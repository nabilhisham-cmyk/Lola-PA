"""Tests for Hermes-PA repo structure and configuration.

Run: python -m pytest tests/ -v
Or:  python tests/test_repo_structure.py

These tests validate the repo itself — not the running Hermes instance.
They catch config drift, missing files, broken YAML, and structural issues
before they reach Railway.
"""
import os
import re
import sys
import yaml
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_yaml(path):
    with open(os.path.join(REPO_ROOT, path)) as f:
        return yaml.safe_load(f)


# ── Config files exist ──────────────────────────────────────────────

class TestConfigFiles:
    def test_config_yaml_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "config.yaml"))

    def test_soul_md_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "SOUL.md"))

    def test_env_example_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, ".env.example"))

    def test_dockerfile_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "Dockerfile.railway"))

    def test_railway_init_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "railway", "railway-init.sh"))

    def test_migration_sql_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "supabase_migration.sql"))

    def test_events_migration_sql_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "supabase_events_migration.sql"))

    def test_seed_script_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "seed_events_data.py"))

    def test_supabase_plugin_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "plugins", "memory", "supabase", "__init__.py"))

    def test_profiles_exist(self):
        for name in ["pa", "events", "ops", "admin"]:
            assert os.path.isdir(os.path.join(REPO_ROOT, "profiles", name)), f"profiles/{name} missing"

    def test_skills_exist(self):
        for name in ["events-ops", "entrepreneur-frameworks"]:
            assert os.path.isdir(os.path.join(REPO_ROOT, "skills", name)), f"skills/{name} missing"


# ── Main config.yaml validity ───────────────────────────────────────

class TestMainConfig:
    @pytest.fixture(scope="class")
    def config(self):
        return _load_yaml("config.yaml")

    def test_parses_as_valid_yaml(self, config):
        assert isinstance(config, dict)

    def test_model_section(self, config):
        assert "model" in config
        assert config["model"].get("default"), "model.default must be set"
        assert config["model"].get("provider"), "model.provider must be set"

    def test_fallback_provider_configured(self, config):
        fallbacks = config.get("fallback_providers", [])
        assert len(fallbacks) > 0, "fallback_providers must not be empty"
        fb = fallbacks[0]
        assert fb.get("provider"), "fallback provider must have a provider field"
        assert fb.get("model"), "fallback provider must have a model field"

    def test_timezone_set(self, config):
        tz = config.get("timezone", "")
        assert tz, "timezone must not be empty"

    def test_memory_provider_is_supabase(self, config):
        assert config.get("memory", {}).get("provider") == "supabase"

    def test_approvals_mode_smart(self, config):
        assert config.get("approvals", {}).get("mode") == "smart"

    def test_session_reset_configured(self, config):
        sr = config.get("session_reset", {})
        assert sr.get("mode") != "none", "session_reset.mode should not be 'none'"

    def test_log_rotation_adequate(self, config):
        log = config.get("logging", {})
        assert log.get("max_size_mb", 0) >= 20, "logging.max_size_mb should be >= 20"
        assert log.get("backup_count", 0) >= 5, "logging.backup_count should be >= 5"

    def test_auxiliary_models_pinned(self, config):
        aux = config.get("auxiliary", {})
        # Vision can stay on a specific model, but lightweight tasks should not be "auto"
        for task in ["compression", "title_generation", "approval"]:
            task_cfg = aux.get(task, {})
            assert task_cfg.get("provider") != "auto", \
                f"auxiliary.{task}.provider should not be 'auto' (wastes main model tokens)"

    def test_config_version_matches_expected(self, config):
        assert config.get("_config_version") == 30, \
            f"_config_version should be 30, got {config.get('_config_version')}"

    def test_no_railway_state_directory(self):
        """railway-state/ should not exist — config drift eliminated."""
        assert not os.path.isdir(os.path.join(REPO_ROOT, "railway", "railway-state")), \
            "railway/railway-state/ should not exist (config drift eliminated)"

    def test_home_mode_is_auto(self, config):
        """Root config must have home_mode: auto (Dockerfile sed overrides for Railway)."""
        assert config.get("terminal", {}).get("home_mode") == "auto", \
            "root config terminal.home_mode must be 'auto' (Dockerfile overrides for Railway)"


# ── Profile configs are delta-only ──────────────────────────────────

class TestProfileConfigs:
    @pytest.mark.parametrize("profile", ["pa", "events"])
    def test_profile_config_is_delta_only(self, profile):
        path = os.path.join(REPO_ROOT, "profiles", profile, "config.yaml")
        with open(path) as f:
            content = f.read()
        line_count = len(content.strip().splitlines())
        assert line_count < 30, \
            f"profiles/{profile}/config.yaml should be delta-only (<30 lines), got {line_count}"

    @pytest.mark.parametrize("profile", ["pa", "events"])
    def test_profile_config_valid_yaml(self, profile):
        path = os.path.join(REPO_ROOT, "profiles", profile, "config.yaml")
        cfg = _load_yaml(path)
        assert isinstance(cfg, dict)

    @pytest.mark.parametrize("profile", ["pa", "events", "ops", "admin"])
    def test_profile_soul_exists(self, profile):
        assert os.path.isfile(os.path.join(REPO_ROOT, "profiles", profile, "SOUL.md"))

    def test_pa_profile_has_mcp(self):
        cfg = _load_yaml("profiles/pa/config.yaml")
        assert "mcp_servers" in cfg, "pa profile should have google-calendar MCP"
        assert "google-calendar" in cfg["mcp_servers"]


# ── Dockerfile.railway ──────────────────────────────────────────────

class TestDockerfile:
    @pytest.fixture(scope="class")
    def dockerfile(self):
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as f:
            return f.read()

    def test_hermes_ref_is_sha_not_main(self, dockerfile):
        """HERMES_REF must be pinned to a commit SHA, not 'main'."""
        match = re.search(r"ARG HERMES_REF=(\S+)", dockerfile)
        assert match, "ARG HERMES_REF not found"
        ref = match.group(1)
        assert ref != "main", "HERMES_REF must not be 'main' — pin to a commit SHA"
        assert len(ref) >= 40, f"HERMES_REF should be a 40-char SHA, got {ref}"

    def test_git_clone_supports_sha(self, dockerfile):
        """Clone command must work with commit SHAs (no --branch for SHAs)."""
        # Should NOT use --branch with HERMES_REF
        assert "git clone --branch" not in dockerfile or \
               "git checkout" in dockerfile, \
            "git clone must support SHA pinning (clone + checkout, not --branch)"

    def test_faster_whisper_installed(self, dockerfile):
        assert "faster-whisper" in dockerfile, \
            "faster-whisper must be in pip install (STT needs it)"

    def test_fastembed_installed(self, dockerfile):
        assert "fastembed" in dockerfile, \
            "fastembed must be in pip install (memory embeddings)"

    def test_fastembed_cache_persistent(self, dockerfile):
        assert "FASTEMBED_CACHE_PATH=/opt/data" in dockerfile, \
            "FASTEMBED_CACHE_PATH must point to persistent /opt/data"

    def test_no_hardcoded_secrets(self, dockerfile):
        """Dockerfile must not contain API keys, tokens, or passwords."""
        # Check for common secret patterns
        secret_patterns = [
            r"sk-[a-zA-Z0-9]{20}",
            r"sb_secret_[a-zA-Z0-9]{20}",
        ]
        for pattern in secret_patterns:
            matches = re.findall(pattern, dockerfile)
            assert len(matches) == 0, f"Potential secret in Dockerfile: {matches}"
        # 64-char hex strings are legit (image digests, SHAs) — skip

    def test_copies_root_configs_not_railway_state(self, dockerfile):
        """Should COPY root config files, not railway/railway-state/."""
        assert "COPY railway/railway-state/" not in dockerfile, \
            "Should not COPY railway/railway-state/ (config drift eliminated)"
        assert "COPY config.yaml" in dockerfile, \
            "Should COPY config.yaml from root (single source of truth)"

    def test_home_mode_override_sed(self, dockerfile):
        """Dockerfile should sed home_mode to 'real' for Railway."""
        assert "home_mode: real" in dockerfile, \
            "Dockerfile should override home_mode to 'real' via sed"

    def test_gh_cli_installed_or_optional(self, dockerfile):
        """GitHub CLI should be installed (or at minimum git auth hook present).
        PA Template has GitHub as optional, so we just check git is available."""
        assert "git clone" in dockerfile, \
            "Dockerfile must clone Hermes source via git"


# ── railway-init.sh ─────────────────────────────────────────────────

class TestRailwayInit:
    @pytest.fixture(scope="class")
    def content(self):
        with open(os.path.join(REPO_ROOT, "railway", "railway-init.sh")) as f:
            return f.read()

    def test_uses_gh_credential_helper(self, content):
        assert "gh auth git-credential" in content, \
            "Should use gh CLI as git credential helper"

    def test_no_git_credentials_file_write(self, content):
        """Should not write .git-credentials file (deprecated approach).
        Only allow mentions in comments, not in actual write commands."""
        # Remove comment lines before checking
        code_lines = [l for l in content.splitlines() if not l.strip().startswith("#")]
        code = "\n".join(code_lines)
        assert ".git-credentials" not in code, \
            "Should not write .git-credentials file (deprecated approach)"

    def test_authenticates_as_hermes_user(self, content):
        assert "s6-setuidgid hermes" in content, \
            "gh auth should run as hermes user, not root"

    def test_warmup_fastembed(self, content):
        assert "fastembed" in content.lower(), \
            "Should warm up fastembed at boot"

    def test_no_hardcoded_secrets(self, content):
        # Check for obvious secret patterns (not env var references)
        lines = content.splitlines()
        for line in lines:
            # Skip lines that reference env vars
            if "${" in line or "$" in line:
                continue
            # Check for long hex strings that look like keys
            if re.search(r"[a-f0-9]{64}", line):
                pytest.fail(f"Potential hardcoded secret in railway-init.sh: {line.strip()}")


# ── Supabase plugin ─────────────────────────────────────────────────

class TestSupabasePlugin:
    @pytest.fixture(scope="class")
    def plugin_path(self):
        return os.path.join(REPO_ROOT, "plugins", "memory", "supabase", "__init__.py")

    @pytest.fixture(scope="class")
    def plugin_source(self, plugin_path):
        with open(plugin_path) as f:
            return f.read()

    def test_plugin_file_exists(self, plugin_path):
        assert os.path.isfile(plugin_path)

    def test_defines_search_schema(self, plugin_source):
        assert "supabase_search" in plugin_source, \
            "Plugin must define supabase_search schema"

    def test_defines_remember_schema(self, plugin_source):
        assert "supabase_remember" in plugin_source, \
            "Plugin must define supabase_remember schema"

    def test_defines_forget_schema(self, plugin_source):
        assert "supabase_forget" in plugin_source, \
            "Plugin must define supabase_forget schema"

    def test_defines_interactions_schema(self, plugin_source):
        assert "supabase_interactions" in plugin_source, \
            "Plugin must define supabase_interactions schema"

    def test_uses_nomic_embed_model(self, plugin_source):
        assert "nomic-ai/nomic-embed-text-v1.5" in plugin_source, \
            "Plugin should use nomic-embed-text-v1.5"

    def test_embed_dim_768(self, plugin_source):
        assert "_EMBED_DIM = 768" in plugin_source, \
            "Embedding dimension must be 768 (nomic-embed-text-v1.5)"

    def test_has_embedder_singleton(self, plugin_source):
        assert "_embedder_lock" in plugin_source, \
            "Plugin should have a thread-safe embedder singleton"

    def test_reads_config_from_env(self, plugin_source):
        assert "SUPABASE_MEMORY_URL" in plugin_source, \
            "Plugin should read SUPABASE_MEMORY_URL from env"
        assert "SUPABASE_MEMORY_KEY" in plugin_source, \
            "Plugin should read SUPABASE_MEMORY_KEY from env"

    def test_no_hardcoded_urls_or_keys(self, plugin_source):
        # Remove docstrings and comments before checking
        lines = plugin_source.splitlines()
        code_lines = []
        in_docstring = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                continue
            if not in_docstring and not stripped.startswith("#"):
                code_lines.append(line)
        code = "\n".join(code_lines)
        # Should not hardcode actual Supabase project URLs
        assert not re.search(r"https://[a-z]{20}\.supabase\.co", code), \
            "Plugin should not hardcode Supabase project URLs"
        assert not re.search(r"sb_secret_\w{20}", code), \
            "Plugin should not hardcode Supabase keys"


# ── .env.example ────────────────────────────────────────────────────

class TestEnvExample:
    @pytest.fixture(scope="class")
    def content(self):
        with open(os.path.join(REPO_ROOT, ".env.example")) as f:
            return f.read()

    def test_has_openai_key(self, content):
        assert "OPENAI_API_KEY" in content

    def test_has_supabase_url(self, content):
        assert "SUPABASE_MEMORY_URL" in content

    def test_has_supabase_key(self, content):
        assert "SUPABASE_MEMORY_KEY" in content

    def test_has_telegram_token(self, content):
        assert "TELEGRAM_BOT_TOKEN" in content

    def test_has_telegram_allowed_users(self, content):
        assert "TELEGRAM_ALLOWED_USERS" in content

    def test_has_github_token(self, content):
        assert "GITHUB_TOKEN" in content

    def test_no_real_secrets(self, content):
        """.env.example should only have placeholders, not real values."""
        # Check no real Supabase URLs
        assert not re.search(r"https://[a-z]{20}\.supabase\.co", content), \
            ".env.example should not contain real Supabase URLs"
        # Check no real bot tokens (format: 123456:ABC-DEF)
        assert not re.search(r"\d{10}:[A-Za-z0-9_-]{35}", content), \
            ".env.example should not contain real Telegram bot tokens"


# ── .gitignore ──────────────────────────────────────────────────────

class TestGitignore:
    @pytest.fixture(scope="class")
    def content(self):
        with open(os.path.join(REPO_ROOT, ".gitignore")) as f:
            return f.read()

    def test_ignores_env(self, content):
        assert ".env" in content, ".gitignore must exclude .env"

    def test_ignores_keys(self, content):
        assert "*.key" in content or "*.keys.json" in content, \
            ".gitignore must exclude key files"

    def test_ignores_state_db(self, content):
        assert "state.db" in content, ".gitignore must exclude state.db"

    def test_ignores_sessions(self, content):
        assert "sessions/" in content, ".gitignore must exclude sessions/"

    def test_ignores_logs(self, content):
        assert "logs/" in content or "*.log" in content, \
            ".gitignore must exclude logs"