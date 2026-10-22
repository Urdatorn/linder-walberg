#!/usr/bin/env bash
# OCR the Linder-Walberg scans with CLLG/Qwen3VL-8B-synth_real, one GH200 per
# array task; each task takes every Nth page, and finished pages are skipped
# on resubmission.
#
#   pilot (start of A, scored against Runeberg's proofread pages):
#     sbatch --array=0 --export=ALL,PAGES=0005-0009,RUN=pilot slurm/ocr.slurm
#   full run:
#     sbatch --array=0-3 slurm/ocr.slurm
#
# Overrides via --export: PAGES (join ranges with '+', since --export
# splits on commas, e.g. PAGES=0005-0009+0028), RUN, BATCH_SIZE, PROMPT, SCALE, EXTRA_ARGS.
#SBATCH --job-name=lw-ocr
#SBATCH --account=naiss2026-3-353-gpu
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gpus=1
#SBATCH --mem=120G
#SBATCH --time=04:00:00
#SBATCH --array=0-3
#SBATCH --output=.logs/%x-%A_%a.out
#SBATCH --error=.logs/%x-%A_%a.err

set -Eeuo pipefail
trap 'status=$?; printf "[%s] ERROR line=%s command=%q status=%s\n" "$(date --iso-8601=seconds)" "$LINENO" "$BASH_COMMAND" "$status" >&2; exit "$status"' ERR

cleland="/nobackup/proj/flash/dionysus/personal/cleland"
repo_dir="$cleland/linder-walberg"
python="$cleland/sphragis_models/.venv/bin/python"   # aarch64: torch 2.13, transformers 4.57.6
run="${RUN:-full}"
out_dir="$repo_dir/ocr_runs/$run"
shard="${SLURM_ARRAY_TASK_ID:-0}"
num_shards="${SLURM_ARRAY_TASK_COUNT:-1}"

cd "$repo_dir"
mkdir -p .logs "$out_dir"

printf '[%s] job_start id=%s array=%s/%s host=%s run=%s pages=%s\n' \
    "$(date --iso-8601=seconds)" "${SLURM_JOB_ID}" "$shard" "$num_shards" "$(hostname)" "$run" "${PAGES:-all}"
module purge
module load GPU/Python/3.13.5-bare-gcc-2025b-eb
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

export HF_HOME="$cleland/hf-cache/huggingface"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONUNBUFFERED=1
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-16}"

# GPU utilisation and memory every two minutes, alongside the progress lines.
nvidia-smi --query-gpu=timestamp,utilization.gpu,memory.used --format=csv,noheader -l 120 &
smi_pid=$!
trap 'kill "$smi_pid" 2>/dev/null || true' EXIT

"$python" ocr/ocr_pages.py \
    --images svegrek \
    --out "$out_dir" \
    --model CLLG/Qwen3VL-8B-synth_real \
    --shard "$shard" --num-shards "$num_shards" \
    --batch-size "${BATCH_SIZE:-16}" \
    --prompt "${PROMPT:-cllg}" \
    --scale "${SCALE:-0.5}" \
    ${PAGES:+--pages "$PAGES"} \
    ${EXTRA_ARGS:-}

# Score the proofread start of A whenever this run has those pages.
if compgen -G "$out_dir/pages/000[5-9].txt" > /dev/null; then
    printf '[%s] eval against Runeberg proofread pages 0005-0009\n' "$(date --iso-8601=seconds)"
    "$python" ocr/eval_runeberg.py --pred "$out_dir/pages" --ref runeberg_txt/Pages --pages 0005-0009 --show 400
fi
printf '[%s] job_complete\n' "$(date --iso-8601=seconds)"
