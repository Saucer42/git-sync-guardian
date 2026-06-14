from gsg import policy


def c(cmd):
    return policy.classify(cmd.split())


def test_clean_is_blocked():
    assert c("git clean -fd").tier == policy.BLOCKED
    assert c("clean -x").tier == policy.BLOCKED


def test_reset_hard_blocked_but_soft_safe():
    assert c("git reset --hard").tier == policy.BLOCKED
    assert c("git reset --soft HEAD~1").tier == policy.SAFE


def test_checkout_force_blocked():
    assert c("git checkout -f main").tier == policy.BLOCKED
    assert c("git checkout --force").tier == policy.BLOCKED
    assert c("git checkout main").tier == policy.SAFE


def test_merge_strategy_option_blocked():
    assert c("git merge -X theirs feature").tier == policy.BLOCKED
    assert c("git merge -Xours feature").tier == policy.BLOCKED
    assert c("git merge --strategy-option=theirs x").tier == policy.BLOCKED


def test_plain_merge_is_guarded():
    assert c("git merge feature").tier == policy.GUARDED


def test_stash_drop_clear_blocked():
    assert c("git stash drop").tier == policy.BLOCKED
    assert c("git stash clear").tier == policy.BLOCKED
    assert c("git stash list").tier == policy.SAFE


def test_rm_cached_recursive_blocked():
    assert c("git rm -r --cached dir").tier == policy.BLOCKED
    assert c("git rm --cached file").tier == policy.SAFE


def test_force_flag_blocked():
    assert c("git push --force").tier == policy.BLOCKED


def test_pull_and_fetch_guarded():
    assert c("git pull").tier == policy.GUARDED
    assert c("git fetch").tier == policy.GUARDED


def test_unknown_is_safe():
    assert c("git status").tier == policy.SAFE
    assert c("git log --oneline").tier == policy.SAFE


def test_config_override_token(tmp_path):
    (tmp_path / ".gsg.toml").write_text(
        '[policy]\noverride_token = "custom token"\nblocked_subcommands = ["status"]\n'
    )
    pol = policy.load_policy(str(tmp_path))
    assert pol.override_token == "custom token"
    assert policy.classify(["git", "status"], pol).tier == policy.BLOCKED
