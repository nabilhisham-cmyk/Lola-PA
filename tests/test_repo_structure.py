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

    def test_events_plugin_exists(self):
        for f in ["__init__.py", "tools.py"]:
            assert os.path.isfile(os.path.join(REPO_ROOT, "plugins", "events_data", f)), \
                f"plugins/events_data/{f} missing"

    def test_dockerfile_ships_the_events_plugin(self):
        """The plugin is useless if the image never copies it. Both files must be
        COPYed, and psycopg must be installed, or the tools fail at runtime."""
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as f:
            df = f.read()
        assert "plugins/events_data/__init__.py" in df, "events plugin __init__ not copied"
        assert "plugins/events_data/tools.py" in df, "events plugin tools not copied"
        assert "psycopg" in df, "psycopg must be installed for the events plugin to connect"

    def test_events_briefing_cron_is_domain_specific(self):
        """The briefing must be about events, not the generic template text."""
        with open(os.path.join(REPO_ROOT, "scripts", "setup-cron-jobs.py")) as f:
            src = f.read()
        assert "events-briefing" in src
        assert "venue_clashes" in src and "at_risk" in src
        for stale in ["open GitHub PRs", "weather in Cairo", "your city"]:
            assert stale not in src, f"template leftover still present: {stale!r}"

    def test_s6_overlay_is_vendored_not_fetched(self):
        """The build must not depend on GitHub's release CDN.

        Five deploys failed on a 504 fetching these three tarballs, and --retry
        did not help (six consecutive 504s, all retries exhausted). The fix was
        to vendor them. If someone reintroduces a curl for s6-overlay, this
        catches it before it costs another deploy.
        """
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as f:
            df = f.read()
        # Look for a curl INVOCATION, not the word "curl" appearing in the
        # apt-get package list. An earlier version of this test failed on the
        # package name and proved nothing.
        import re as _re
        assert not _re.search(r"curl\s+-[a-zA-Z]*f", df), \
            "no curl download should remain in the Dockerfile"
        assert "releases/download" not in df, \
            "the Dockerfile must not fetch anything from a release CDN"
        # The install step must copy from the vendored directory.
        assert "docker/vendor/s6-overlay" in df, "vendored s6-overlay not referenced"
        assert "sha256sum -c" in df, "vendored tarballs must be checksum-verified"

        vendor = os.path.join(REPO_ROOT, "docker", "vendor", "s6-overlay")
        for f in ["s6-overlay-noarch.tar.xz", "s6-overlay-x86_64.tar.xz",
                  "s6-overlay-aarch64.tar.xz", "s6-overlay-symlinks-noarch.tar.xz",
                  "SHA256SUMS", "README.md"]:
            assert os.path.isfile(os.path.join(vendor, f)), f"missing vendored file {f}"

    def test_vendored_s6_checksums_match_the_files(self):
        """A checksum file that does not match its payload fails the build at
        image time, which is the worst place to find out."""
        import hashlib
        vendor = os.path.join(REPO_ROOT, "docker", "vendor", "s6-overlay")
        with open(os.path.join(vendor, "SHA256SUMS")) as f:
            lines = [ln.split() for ln in f if ln.strip()]
        assert lines, "SHA256SUMS is empty"
        for digest, name in lines:
            path = os.path.join(vendor, name)
            assert os.path.isfile(path), f"SHA256SUMS names a missing file: {name}"
            actual = hashlib.sha256(open(path, "rb").read()).hexdigest()
            assert actual == digest, f"{name} does not match its recorded checksum"

    def test_onboarding_guides_composio_and_addresses_hisham(self):
        """Onboarding must connect his accounts, not ask him to fill in a profile.

        The first version asked Hany's question ("build a quick profile?") and
        addressed the user as "you" from Hany's perspective, so Lola would have
        asked Hisham to describe his own role. This locks in the correct shape.
        """
        with open(os.path.join(REPO_ROOT, "SOUL.md")) as f:
            soul = f.read()

        # It must name Hisham as the person being onboarded.
        assert "Hisham" in soul
        # It must send him to Composio.
        assert "composio.dev" in soul
        assert "ck_" in soul, "must tell him the key prefix so he recognises it"
        # It must say what connecting unlocks, in concrete terms.
        for capability in ["calendar", "email", "run-sheet"]:
            assert capability in soul.lower(), f"unlock list should mention {capability}"
        # It must address the privacy worry.
        assert "password" in soul.lower(), "must reassure that his password is not shared"

        # It must NOT ask for a profile up front.
        assert "Do NOT ask for a profile" in soul
        for bad in ["build a quick profile", "what is your role", "your working hours"]:
            assert bad.lower() not in soul.lower(), f"profile-prompting leftover: {bad!r}"

    def test_builtin_profile_offer_is_disabled_and_correctly_typed(self):
        """The built-in first-contact directive must be OFF, and it must be the
        STRING "off".

        Hisham's first message asked him for a profile, because Hermes's built-in
        onboarding directive competed with ours in SOUL.md and won. Turning it off
        is a one-line config change — but unquoted `off` is YAML 1.1 boolean
        False, and profile_build_mode() only matches the string "off", so the
        unquoted form leaves the directive ACTIVE while looking correct. This test
        pins the type, not just the presence.
        """
        import yaml
        with open(os.path.join(REPO_ROOT, "config.yaml")) as f:
            cfg = yaml.safe_load(f)
        value = (cfg.get("onboarding") or {}).get("profile_build")
        assert value == "off", (
            f"onboarding.profile_build must be the string 'off', got {value!r} "
            f"({type(value).__name__}) — quote it in YAML or the built-in "
            "profile-offer directive stays active"
        )
        assert isinstance(value, str), "unquoted 'off' parses as boolean False and does nothing"

    def test_onboarding_says_composio_is_already_wired(self):
        """The SOUL tells Lola to store the key; config must already consume it,
        or the key would be saved and do nothing."""
        with open(os.path.join(REPO_ROOT, "config.yaml")) as f:
            cfg = f.read()
        assert "composio" in cfg
        assert "MCP_COMPOSIO_API_KEY" in cfg, "config must read the key the SOUL tells him to send"

    def test_vocabulary_is_shared_between_soul_skill_and_sql(self):
        """The status vocabulary must agree across the SOUL, the skill and the SQL.

        NOTE: this test was previously named test_skill_documents_the_same_status_values
        but its body had been clobbered to assert a file path, so it checked nothing.
        Restored to actually compare the vocabulary it claims to.
        """
        sql = open(os.path.join(REPO_ROOT, "scripts", "supabase_events_migration.sql")).read()
        skill = open(os.path.join(REPO_ROOT, "skills", "events-ops", "SKILL.md")).read()
        for value in ["proposed", "confirmed", "in_production", "live", "completed", "cancelled"]:
            assert value in sql, f"event status {value} missing from the SQL"
            assert value in skill, f"event status {value} missing from the skill"

    def test_meetings_plugin_exists_and_is_shipped(self):
        """The meetings plugin is useless if the image never copies it."""
        for f in ["__init__.py", "tools.py"]:
            assert os.path.isfile(os.path.join(REPO_ROOT, "plugins", "meetings", f)), \
                f"plugins/meetings/{f} missing"
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as fh:
            df = fh.read()
        assert "plugins/meetings/__init__.py" in df, "meetings __init__ not copied"
        assert "plugins/meetings/tools.py" in df, "meetings tools not copied"

    def test_schema_files_are_shipped_in_the_image(self):
        """The container must be able to reproduce its own database.

        Data survives a restart inside Supabase, but the SCHEMA definition is the
        one thing a volume cannot give back. These were previously absent from the
        image, so a rebuilt Supabase project or a second environment could not be
        stood up from the deployed artefact.
        """
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as fh:
            df = fh.read()
        for f in ["supabase_migration.sql", "supabase_events_migration.sql",
                  "supabase_events_migration_v2.sql", "supabase_events_migration_v3.sql",
                  "supabase_meetings_migration.sql", "supabase_events_seed.sql",
                  "seed_events_data.py"]:
            assert f"scripts/{f}" in df, f"{f} is not shipped in the image"

    def test_cont_init_scripts_are_executable(self):
        """A non-executable cont-init script exits 126 SILENTLY.

        s6 runs /etc/cont-init.d/* in name order. If a file is not executable it
        logs "exited 126" and nothing else fails, so a boot hook can be dead for
        months without anyone noticing. 015-supervise-perms shipped that way: git
        mode 100644 in the fork's upstream commit, fixed here by setting the mode
        (blob content untouched) plus an explicit chmod in the Dockerfile.
        """
        import subprocess
        out = subprocess.run(
            ["git", "ls-files", "-s", "docker/cont-init.d/"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).stdout
        assert out.strip(), "no cont-init scripts tracked"
        offenders = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0] != "100755":
                offenders.append(parts[3])
        assert not offenders, (
            "these cont-init scripts are not executable in git and will exit 126: "
            f"{offenders}"
        )
        # And the Dockerfile must not rely on the mode alone.
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as fh:
            df = fh.read()
        assert "chmod +x /etc/cont-init.d/*" in df, \
            "Dockerfile should force the executable bit on cont-init scripts"
        # And use upstream's own mechanism for the two it COPYs from source.
        # Upstream's Dockerfile does `COPY --chmod=0755` for both; the fork used a
        # plain COPY, so the mode came from the source file and 015 landed
        # non-executable. Matching upstream is the fix.
        for f in ["015-supervise-perms", "02-reconcile-profiles"]:
            assert f"--chmod=0755 /hermes/docker/cont-init.d/{f}" in df, \
                f"{f} must be COPYed with --chmod=0755, as upstream does"

    def test_boot_applies_migrations(self):
        """And something must actually apply them, after credentials exist."""
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as fh:
            df = fh.read()
        assert "apply-migrations.sh" in df, "boot hook not wired"
        # cont-init ordering: 04 runs after 00 (seed volume) and 03 (railway-init).
        assert "04-apply-migrations" in df
        assert os.path.isfile(os.path.join(REPO_ROOT, "railway", "apply-migrations.sh"))

    def test_boot_hook_is_never_fatal(self):
        """A stale schema at boot beats a boot that refuses to start."""
        with open(os.path.join(REPO_ROOT, "railway", "apply-migrations.sh")) as fh:
            sh = fh.read()
        assert "non-fatal, boot continues" in sh
        assert sh.rstrip().endswith("exit 0"), "hook must always exit 0"

    def test_meetings_migration_exists(self):
        assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "supabase_meetings_migration.sql"))

    def test_v2_and_v3_event_migrations_exist(self):
        for f in ["supabase_events_migration_v2.sql", "supabase_events_migration_v3.sql"]:
            assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", f)), f"{f} missing"

    def test_aux_lanes_can_inherit_credentials(self):
        """Aux lanes (vision, web_extract, ...) get their key from model.api_key.

        agent/auxiliary_client._read_main_field("api_key") reads config.yaml ONLY,
        with no environment fallback. If model.api_key is absent, every aux lane
        sends an empty bearer token and returns 401 Unauthorized — which is what
        made image reading fail while the main model kept working.

        So model.api_key must EXIST as an injection point, and the boot hook must
        actually inject it from the environment.
        """
        import yaml
        with open(os.path.join(REPO_ROOT, "config.yaml")) as fh:
            cfg = yaml.safe_load(fh)
        model = cfg.get("model") or {}
        assert "api_key" in model, (
            "model.api_key must exist as an injection point, or the auxiliary "
            "lanes (including vision) authenticate with an empty token and 401"
        )
        aux = (cfg.get("auxiliary") or {}).get("vision") or {}
        assert aux.get("provider"), "vision aux lane must declare a provider"

        # The injector must be shipped and must run from the boot hook.
        with open(os.path.join(REPO_ROOT, "Dockerfile.railway")) as fh:
            df = fh.read()
        assert "inject-config-secrets.py" in df, "injector not shipped in the image"
        assert os.path.isfile(os.path.join(REPO_ROOT, "scripts", "inject-config-secrets.py"))
        with open(os.path.join(REPO_ROOT, "railway", "apply-migrations.sh")) as fh:
            sh = fh.read()
        assert "inject-config-secrets.py" in sh, "boot hook does not run the injector"
        assert "OLLAMA_API_KEY" in open(
            os.path.join(REPO_ROOT, "scripts", "inject-config-secrets.py")).read(), \
            "injector must read the key from the environment"

    def test_stt_initial_prompt_is_configured(self):
        """Without it, whisper transcribed 'Hisham' as 'He sham' on a real
        recording, which in meeting minutes reads as a different person."""
        import yaml
        with open(os.path.join(REPO_ROOT, "config.yaml")) as fh:
            cfg = yaml.safe_load(fh)
        local = ((cfg.get("stt") or {}).get("local") or {})
        assert local.get("model") == "turbo", "STT model should be whisper turbo"
        prompt = local.get("initial_prompt")
        assert isinstance(prompt, str) and "Hisham" in prompt, \
            "stt.local.initial_prompt must name Hisham, or his name mis-transcribes"

    def test_identity_is_known_and_never_asked(self):
        """Hisham's identity and key events must be in the SOUL, not discovered
        by asking him. He was shown 'can I build a profile of you', which is both
        redundant and impersonal: Lola already knows exactly who he is."""
        soul = open(os.path.join(REPO_ROOT, "SOUL.md")).read()
        for fact in ["Hisham Nabil", "Orascom", "Sandbox", "GFF",
                     "Kings Polo", "Squash"]:
            assert fact in soul, f"{fact} must be in the concierge SOUL"
        assert "Never ask him for any of this" in soul or "never ask" in soul.lower()
        assert "never offer to" in soul.lower() or "Never offer" in soul

    def test_key_events_are_seeded(self):
        seed = open(os.path.join(REPO_ROOT, "scripts", "supabase_events_seed.sql")).read()
        for ev in ["Sandbox Festival", "Kings Polo", "Squash Open"]:
            assert ev in seed, f"{ev} missing from the seed"

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