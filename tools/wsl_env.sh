export FORGE_PROVIDER_ENVS=$HOME/mm/root/envs
# The checkout this script lives in (source it from any worktree); FORGE_ROOT overrides.
R=${FORGE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
export PYTHONPATH=$R/src:$R:$R/flagships:$(ls -d $R/providers/*/ | sed "s#/\$##" | tr "\n" ":")
export PATH=$HOME/mm/root/envs/${FORGE_PY_ENV:-battery}/bin:$PATH
export TMPDIR=/tmp
