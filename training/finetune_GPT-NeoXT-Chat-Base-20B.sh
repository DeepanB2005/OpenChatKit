DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

netif=lo
export GLOO_SOCKET_IFNAME=${netif}
export NCCL_SOCKET_IFNAME=${netif}
export MODEL_NAME=GPT-Neo-XT-Chat-Base-20B

export SHOW_DATA=0

BASE_MODEL="${DIR}/../pretrained/GPT-NeoX-20B/EleutherAI_gpt-neox-20b/"

TOTAL_STEPS=${FINETUNE_TOTAL_STEPS:-20000}
CHECKPOINT_STEPS=${FINETUNE_CHECKPOINT_STEPS:-100}
CHECKPOINT_PATH=${FINETUNE_CHECKPOINT_PATH:-"${DIR}/../model_ckpts/${MODEL_NAME}"}

DATASETS="\
${DIR}/../data/OIG/files/unified_ni.jsonl:0.2,\
${DIR}/../data/OIG/files/unified_p3.jsonl:0.5,\
${DIR}/../data/OIG/files/unified_flan.jsonl:0.2,\
${DIR}/../data/OIG/files/unified_chip2.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_rallio_safety_and_prosocial.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_soda_dialog.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_unifiedskg_instructions.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_merged_code_xp3.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_oscar_en_sample_dialog.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_ul2_plus_oscar_en_sample_dialog.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_multi_news.jsonl:0.05,\
${DIR}/../data/OIG/files/unified_openai_summarize_tldr.jsonl:0.05,\
${DIR}/../data/OIG/files/unified_squad_v2.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_nq.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_poetry_instructions.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_sqlv2.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_unnatural_instructions.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_conv_finqa.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_essays.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_plot_screenplay_books_dialog.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_grade_school_math_instructions.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_mathqa_flanv2_kojma_cot.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_joke_explanations.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_cuad.jsonl:0.01,\
${DIR}/../data/OIG/files/unified_abstract_infill.jsonl:0.1,\
${DIR}/../data/OIG/files/unified_image_prompts_instructions.jsonl:0.01 \
"

ARGS="--model-name ${BASE_MODEL} \
--tokenizer-name ${BASE_MODEL} \
--project-name together \
--model-type gptneox \
--optimizer adam \
--seed 42 \
--load-pretrained-model true \
--task-name \
"${DATASETS}" \
--checkpoint-path ${CHECKPOINT_PATH} \
--total-steps ${TOTAL_STEPS} --warmup-steps 10 --train-warmup-steps 0 \
--checkpoint-steps ${CHECKPOINT_STEPS} \
--lr 1e-6 --seq-length 2048 --batch-size 64 --micro-batch-size 1 --gradient-accumulate-step 1 \
--dist-url tcp://127.0.0.1:7033 \
--num-layers 6 --embedding-dim 6144 \
--world-size 8 --pipeline-group-size 8 --data-group-size 1 \
--job-id 0 --net-interface ${netif} \
--fp16 \
--dp-backend nccl \
--dp-mode allreduce \
--pp-mode gpipe --profiling no-profiling"


