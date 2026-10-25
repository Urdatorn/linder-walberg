#!/usr/bin/env bash
# Search the AncientGreek corpus for Linder & Walberg's Greek examples.
#   sbatch slurm/locorum.slurm
#SBATCH --job-name=lw-locorum
#SBATCH --account=naiss2026-3-353-gpu
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=48
#SBATCH --gpus=1
#SBATCH --mem=200G
#SBATCH --time=03:00:00
#SBATCH --output=.logs/%x-%j.out
#SBATCH --error=.logs/%x-%j.err

set -Eeuo pipefail
cleland="/nobackup/proj/flash/dionysus/personal/cleland"
cd "$cleland/linder-walberg"
mkdir -p .logs
module purge
module load GPU/Python/3.13.5-bare-gcc-2025b-eb
corpus=$(ls -d "$cleland"/hf-cache/huggingface/hub/datasets--Ericu950--AncientGreek/snapshots/*/data)
printf '[%s] job_start host=%s cpus=%s corpus=%s\n' "$(date --iso-8601=seconds)" "$(hostname)" "$SLURM_CPUS_PER_TASK" "$corpus"
export PYTHONUNBUFFERED=1
"$cleland/sphragis_models/.venv/bin/python" locorum/find_sources.py --corpus "$corpus" --workers "$SLURM_CPUS_PER_TASK"
printf '[%s] job_complete\n' "$(date --iso-8601=seconds)"
