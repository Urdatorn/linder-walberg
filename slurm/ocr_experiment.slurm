#!/usr/bin/env bash
# Retry-policy experiment: problem strips under several scales and prompts.
#   sbatch --export=ALL,CASES=0006:4+0008:2 slurm/ocr_experiment.slurm
#SBATCH --job-name=lw-ocr-exp
#SBATCH --account=naiss2026-3-353-gpu
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --gpus=1
#SBATCH --mem=120G
#SBATCH --time=01:00:00
#SBATCH --output=.logs/%x-%j.out
#SBATCH --error=.logs/%x-%j.err

set -Eeuo pipefail
cleland="/nobackup/proj/flash/dionysus/personal/cleland"
cd "$cleland/linder-walberg"
module purge
module load GPU/Python/3.13.5-bare-gcc-2025b-eb
export HF_HOME="$cleland/hf-cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
mkdir -p ocr_runs/experiments
printf '[%s] job_start id=%s host=%s cases=%s\n' "$(date --iso-8601=seconds)" "$SLURM_JOB_ID" "$(hostname)" "$CASES"
"$cleland/sphragis_models/.venv/bin/python" ocr/experiment_strips.py --images svegrek \
    --out "ocr_runs/experiments/strips-$SLURM_JOB_ID.json" --cases "${CASES//+/,}"
printf '[%s] job_complete\n' "$(date --iso-8601=seconds)"
