this is a project to re-ocr the linder-walberg swedish-grc lexicon images; the latest ocr was done in 2013 and has tons of errors and has never been proofread. this year angleraud et al made a model that is extremely good, https://arxiv.org/abs/2603.02803

the checkpoints are at https://huggingface.co/CLLG
 we will take the best one and prepare to run a slurm job on the images in the zip. 
read claude.md and skills and memories for info of running inference on ARM GH200 compute nodes on this arrhenius slurm cluster.
