DIR=$(cd -- "$( dirname -- "${BASH_SOffbsdhbfjlkwg
export GLOO_SOCKET_IFNAME=${netif}
export NCCL_SOCKET_IFNAME=${netif}
export MODEL_NAME=llama-2-7b-32k-mqa

export SHOW_DATA=1

BASE_MODEL="${DIR}/../pretrained/Llama-2-7B-32K-beta/togethercomputer_Llama-2-7B-32K-beta"

TOTAL_STEPS=${FINETUNE_TOTAL_STEPS:-10}
CHECKPOINT_STEPS=${FINETUNE_CHECKPOINT_STEPS:-10}
CHECKPOINT_PATH=${FINETUNE_CHECKPOINT_PATH:-"${DIR}/../model_ckpts/${MODEL_NAME}"}

DATASETS="https://huggingface.co/datasets/togethercomputer/Long-Data-Collections/resolve/main/fine-tune/natural_questions_10_200_docs.jsonl.zst:1"

ARGS="--model-name ${BASE_MODEL} \
--tokenizer-name ${BASE_MODEL} \
--project-name together \
--model-type llama \
--optimizer adam \
--seed 42 \
--load-pretrained-model true \
--task-name \
"${DATASETS}" \
--checkpoint-path ${CHECKPOINT_PATH} \
--total-steps ${TOTAL_STEPS} --warmup-steps 0 --train-warmup-steps 0 \
--checkpoint-steps ${CHECKPOINT_STEPS} \
--lr 2e-5 --seq-length 32768 --batch-size 4 --micro-batch-size 1 --gradient-accumulate-step 1 \
--dist-url tcp://127.0.0.1:7033 \
--num-layers 4 --embedding-dim 4096 \
--world-size 8 --pipeline-group-size 8 --data-group-size 1 \
--job-id 0 --net-interface ${netif} \
--fp16 \
--dp-backend nccl \
--dp-mode allreduce \
--pp-mode gpipe --profiling no-profiling"

(trap 'kill 0' SIGINT; \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 0 --rank 0 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 1 --rank 1 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 2 --rank 2 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 3 --rank 3 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 4 --rank 4 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 5 --rank 5 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 6 --rank 6 \
    & \
python ${DIR}/dist_clm_train.py $(echo ${ARGS}) --cuda-id 7 --rank 7 \
    & \
wait)
