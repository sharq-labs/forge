export FORGE_PROVIDER_ENVS=$HOME/mm/root/envs
R=/mnt/d/forge-b13
export PYTHONPATH=$R/src:$R:$R/flagships:$(ls -d $R/providers/*/ | sed "s#/\$##" | tr "\n" ":")
export PATH=$HOME/mm/root/envs/${FORGE_PY_ENV:-battery}/bin:$PATH
export TMPDIR=/tmp
