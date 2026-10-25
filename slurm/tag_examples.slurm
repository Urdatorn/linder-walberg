#!/usr/bin/env bash
# Tag the Greek examples with Stoicheia's tagger-parser.
#   sbatch slurm/tag_examples.slurm
#SBATCH --job-name=lw-tag
#SBATCH --account=naiss2026-3-353-gpu
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=.logs/%x-%j.out
#SBATCH --error=.logs/%x-%j.err
set -Eeuo pipefail
cleland="/nobackup/proj/flash/dionysus/personal/cleland"
cd "$cleland/linder-walberg"
module purge
module load GPU/Python/3.13.5-bare-gcc-2025b-eb
export HF_HOME="$cleland/hf-cache/huggingface" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
printf '[%s] job_start host=%s\n' "$(date --iso-8601=seconds)" "$(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
"$cleland/sphragis_models/.venv/bin/python" locorum/tag_examples.py --batch 64
printf '[%s] job_complete\n' "$(date --iso-8601=seconds)"
