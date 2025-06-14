import argparse
import time
import random
import numpy as np
import torch
import torch.autograd.profiler as profiler
from tasks.data_loaders.data_utils import get_ul2r_train_data_loader
from modules.utils import gpt_loss_func
from modules.tokenizer import build_tokenizer
from pipeline_parallel.dist_pp_utils import get_pp_module

from transformers import AutoConfig
import datasets

from utils.dist_args_utils import *
from utils.dist_checkpoint_utils import *
from utils.logging_utils import *
from comm.comm_utils import *


def test_loop(args, pipe, device, test_data_loader):
    print("no impl for testing, skip.")


def train_loop(args, pipe, device, train_data_loader, test_data_loader):
    
    print('training starts......')

    pipe.model.train() # Flag .training to True to enable Dropout
    
    use_dp = (args.world_size != args.pipeline_group_size)
    if use_dp:
        # dp_comm = get_data_parallel_comm()
        dp_rank = get_data_parallel_rank()
        dp_size = get_data_parallel_world_size()
    else:
        dp_rank = 0
        dp_size = 1
    pp_comm = get_pipeline_parallel_comm()
    
    stop_flag = torch.zeros(1, dtype=torch.int64).to(device)
    
    input_ids = torch.zeros(
        [args.batch_size, args.seq_length], 
        dtype=torch.int64
    ).to(device)
    
    prefix_masks = torch.zeros(
        [args.batch_size, args.seq_length], 
        dtype=torch.uint8
    ).to(device)
    
    do_sync_before_save = (args.dp_mode in ['local'] and use_dp)
    
    if get_pipeline_parallel_rank() == 0 and dp_rank == 0:
        
        for i, data in enumerate(train_data_loader):
            if i < pipe.global_step:
                continue
                
            if use_dp:
                get_data_parallel_comm().broadcast(stop_flag, 0)
            pp_comm.broadcast(stop_flag, 0)
            
            if stop_flag.item() == 1:
                break
            
            input_ids_global = data['input_ids'].to(torch.int64).to(device)
            prefix_masks_global = data['prefix_masks'].to(torch.uint8).to(device)
            
            input_ids_list = input_ids_global.chunk(dp_size)
            prefix_masks_list = prefix_masks_global.chunk(dp_size)
            
            if use_dp:
                for j in range(1, dp_size):
                    get_data_parallel_comm().send(
                        input_ids_list[j], j,
                    )
                    get_data_parallel_comm().send(
                        prefix_masks_list[j], j,
                    )
                
            input_ids = input_ids_list[0]
            prefix_masks = prefix_masks_list[0]
            
            pp_comm.broadcast(input_ids, 0)
            pp_comm.broadcast(prefix_masks, 0)
            
            labels = input_ids.clone()
            current_iter_time = pipe.sgd_iter(
                input_ids, labels, aux_input_data={'prefix_masks': prefix_masks}, loss_func=gpt_loss_func
            )
            
            if args.evaluation_steps > 0 and pipe.global_step % args.evaluation_steps == 0:
                test_loop(args, pipe, device, test_data_loader)
            
            if pipe.global_step % args.checkpoint_steps == 0:
                if do_sync_before_save:
                    pipe.dp_optim.allreduce_parameters()
                if dp_rank == 0:
                    save_checkpoint(pipe, args)
                if do_sync_before_save:
                    pipe.dp_optim.rollback_parameters()
            
            if pipe.global_step >= args.total_steps:
                stop_flag.data[:] = 1
            
    elif get_pipeline_parallel_rank() == 0:
        
        while True:
            
            get_data_parallel_comm().broadcast(stop_flag, 0)
            pp_comm.broadcast(stop_flag, 0)
            if stop_flag.item() == 1:
                break
                
            get_data_parallel_comm().recv(
                input_ids, 0,
            )
            get_data_parallel_comm().recv(
                prefix_masks, 0,
            )
            pp_comm.broadcast(input_ids, 0)
            pp_comm.broadcast(prefix_masks, 0)
            
            labels = input_ids.clone()
            current_iter_time = pipe.sgd_iter(
                input_ids, labels, aux_input_data={'prefix_masks': prefix_masks}, loss_func=gpt_loss_func)
            
            if args.evaluation_steps > 0 and pipe.global_step % args.evaluation_steps == 0:
                test_loop(args, pipe, device, test_data_loader)
                
            if pipe.global_step % args.checkpoint_steps == 0:
                if do_sync_before_save:
                    pipe.dp_optim.allreduce_parameters()
                if dp_rank == 0:
                    save_checkpoint(pipe, args)
                if do_sync_before_save:
                    pipe.dp_optim.rollback_parameters()
            
            
    elif get_pipeline_parallel_rank()  == args.pipeline_group_size - 1:
        
        while True:
            
            pp_comm.broadcast(stop_flag, 0)
            if stop_flag.item() == 1:
                break
                
            pp_comm.broadcast(input_ids, 0)
            pp_comm.broadcast(prefix_masks, 0)
            labels = input_ids.clone()
            labels[prefix_masks.bool()] = -100 # mask prefix part
            current_iter_time = pipe.sgd_iter(
                input_ids, labels, loss_func=gpt_loss_func, aux_input_data={'prefix_masks': prefix_masks}
            )
            
            if args.evaluation_steps > 0 and pipe.global_step % args.evaluation_steps == 0:
                test_loop(args, pipe, device, test_data_loader)
                
            if pipe.global_step % args.checkpoint_steps == 0:
                if do_sync_before_save:
                    pipe.dp_optim.allreduce_parameters()
                if dp_rank == 0:
                    save_checkpoint(pipe, args)
                    pipe.save_on_disk(args.checkpoint_path)
                if do_sync_before_save:
                    pipe.dp_optim.rollback_parameters()
    else:
        while True:
            pp_comm.broadcast(stop_flag, 0)
            if stop_flag.item() == 1:
                break
            pp_comm.broadcast(input_ids, 0)
            pp_comm.broadcast(prefix_masks, 0)
            current_iter_time = pipe.sgd_iter(None, None, aux_input_data={'prefix_masks': prefix_masks})
            
            if args.evaluation_steps > 0 and pipe.global_step % args.evaluation_steps == 0:
                test_loop(args, pipe, device, test_data_loader)
                
            if pipe.global_step % args.checkpoint_steps == 0:
                if do_sync_before_save:
                    pipe.dp_optim.allreduce_parameters()
                if dp_rank == 0:
                    save_checkpoint(pipe, args)
                if do_sync_before_save:
                    pipe.dp_optim.rollback_parameters()
        

def main():
    parser = argparse.ArgumentParser(description='Gpipe-GPT')
    add_device_arguments(parser)
    add_torch_distributed_arguments(parser)
    add_model_arguments(parser)
    add_task_arguments(parser)
    add_training_hyper_parameter_arguments(parser)
    add_mixed_precision_arguments(parser)
    add_parallel_schema_arguments(parser)
    parser.add_argument('--model-name', type=str, default='gpt2', metavar='S',
                        help='model name or path')
    parser.add_argument('--tokenizer-name', type=str, default='gpt2', metavar='S',
                        help='tokenizer name or path')
    parser.add_argument('--model-type', type=str, default='gpt2', metavar='S',
                        help='model name or path')
    parser.add_argument('--checkpoint-path', type=str, default='model_checkpoints/gpt2')
    parser.add_argument('--task-name', type=str, default='cot', metavar='S',
                        help='task name')
    parser.add_argument('--warmup-steps', type=int, default=0, help='-')
    parser.add_argument('--train-warmup-steps', type=int, default=0, help='-')
    parser.add_argument('--total-steps', type=int, default=None, help='-')
    parser.add_argument('--load-pretrained-model', 
                        type=lambda x: x.lower()=='true', default=True, metavar='S',
                        help='load pretrained model or not.')
    parser.add_argument('--load-checkpoint', 
                        type=lambda x: x.lower()=='true', default=True, metavar='S',
                        help='load pretrained model or not.')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--profiling', type=str, default='no-profiling', metavar='S',
                        help='enable which profiling? default: tidy mode')
    parser.add_argument('--trace-postfix', type=str, default='default', metavar='S',
                        help='postfix of the tracing file name.')
    parser.add_argument('--evaluation-steps', 
                        type=int, default=0, metavar='S',
                        help='every x steps, do evaluation. (0 means do not do evaluation)')
    parser.add_argument('--evaluation-data',
                        type=str, default=None, help="path of eval data in jsonl")
    parser.add_argument('--evaluation-num-batch',
                        type=
        device = torch.device('cuda', args.cuda_id)
    else:
        device = torch.device('cpu')
        
    init_communicators(args)
    
    use_dp = (args.world_size != args.pipeline_group_size)
    if use_dp:
        dp_comm = get_data_parallel_comm()
        dp_rank = get_data_parallel_rank()
        dp_size = get_data_parallel_world_size()
    else:
        dp_rank = 0
        dp_size = 1
    
    config = AutoConfig.from_pretrained(args.model_name)
    
    # num layer globally
    if hasattr(config, 'num_hidden_layers'):
        args.max_layers = config.num_hidden_layers
    elif hasattr(config, 'num_layers'):
        args.max_layers = config.num_layers 
    else:
        args.max_layers = config.n_layer
    
    tokenizer = build_tokenizer(args)
    tokenizer.model_max_length = args.seq_length
    # config.vocab_size = tokenizer.vocab_size
    config.bos_token_id = tokenizer.bos_token_id
    config.eos_token_id = tokenizer.eos_token_id
    config.pad_token_id = tokenizer.pad_token_id
    print("token vocab size:", config.vocab_size)
    
    if get_pipeline_parallel_rank() == 0 and dp_rank == 0:
        train_data_loader = get_ul2r_train_data_loader(args, tokenizer)
    else:
        train_data_loader = None
        
    test_data_loader = None
        
    if args.total_steps is None:
        args.total_steps = len(train_data_loader)
    
    use_dp = (args.world_size != args.pipeline_group_size)
    if use_dp:
        print("Running ", args.pp_mode, " with data parallel.")
    else:
        print("Running ", args.pp_mode, " without data parallel.")
    
    pipe = get_pp_module(args, config, device, use_dp)
    
    if args.load_checkpoint:
        load_checkpoint(pipe, args)

    if args.fp16:
        pipe.optimizer.reload_model_params()
        
    if args.model_type == 'gptj':
        # make sure, causal mask is here.
        max_positions = config.n_positions
        for module in pipe.model.model:
            if hasattr(module, 'attn'):
                print('put back causal mask')
                module.attn.bias[:] = torch.tril(torch.ones((max_positions, max_positions), dtype=torch.uint8)).view(
                    1, 1, max_positions, max_positions
                )

    if args.profiling == 'no-profiling':
        train_loop(args, pipe, device, train_data_loader, test_data_loader)
    else:
        prefix = './trace_json/gpt3_' + args.pp_mode
        if use_dp:
            prefix = prefix + '_' + args.dp_mode
        trace_file = prefix + get_learning_arguments_str(args) + get_model_arguments_str(args) + \
                     get_dist_arguments_str(args) + get_mixed_precision_arguments_str(args) + '_' + \
                     args.profiling + '_' + args.trace_postfix + '.json'
        if args.profiling == 'tidy_profiling':
            try:
                train_loop(args, pipe, device, train_data_loader, test_data_loader)
            except Exception as e:
                raise e
                print(get_pipeline_parallel_rank(), e)
            pipe.export_profiling_result(filename=trace_file)
        elif args.profiling == 'pytorch_profiling':
            with profiler.profile(profile_memory=True, use_cuda=args.use_cuda) as prof:
                train_loop(args, pipe, device, train_data_loader, test_data_loader)
            print(prof.key_averages().table())
            prof.export_chrome_trace(trace_file)
        else:
            print("No recognized profiler?")
            assert False
    print(get_pipeline_parallel_rank(), 'finished.')

if __name__ == '__main__':
    main()
