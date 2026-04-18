import base64
import shlex

from backend.core.config import CONTAINER_USER_HOME_ROOT


def normalize_public_key(public_key: str) -> str:
    return public_key.strip()


def normalize_public_keys(public_keys: list[str]) -> list[str]:
    normalized_items = [normalize_public_key(item) for item in public_keys]
    normalized_items = [item for item in normalized_items if item]
    return list(dict.fromkeys(normalized_items))


def render_authorized_keys_text(public_keys: list[str]) -> str:
    if not public_keys:
        return ""
    return "\n".join(public_keys) + "\n"


def build_sync_command(linux_username: str, linux_uid: int, linux_gid: int, authorized_keys_text: str) -> str:
    payload_b64 = base64.b64encode(authorized_keys_text.encode("utf-8")).decode("ascii")
    quoted_username = shlex.quote(linux_username)
    quoted_home_root = shlex.quote(CONTAINER_USER_HOME_ROOT)
    quoted_linux_uid = shlex.quote(str(int(linux_uid)))
    quoted_linux_gid = shlex.quote(str(int(linux_gid)))
    quoted_payload = shlex.quote(payload_b64)
    return f"""
set -e
USERNAME={quoted_username}
HOME_ROOT={quoted_home_root}
TARGET_UID={quoted_linux_uid}
TARGET_GID={quoted_linux_gid}
PAYLOAD_B64={quoted_payload}
GROUP_NAME="$USERNAME"
HOME_DIR="$HOME_ROOT/$USERNAME"

if getent group "$GROUP_NAME" >/dev/null; then
  CURRENT_GID="$(getent group "$GROUP_NAME" | cut -d: -f3)"
  if [ "$CURRENT_GID" != "$TARGET_GID" ]; then
    groupmod -g "$TARGET_GID" "$GROUP_NAME"
  fi
else
  groupadd -g "$TARGET_GID" "$GROUP_NAME"
fi

if getent passwd "$USERNAME" >/dev/null; then
  CURRENT_UID="$(id -u "$USERNAME")"
  CURRENT_GID="$(id -g "$USERNAME")"
  CURRENT_HOME="$(getent passwd "$USERNAME" | cut -d: -f6)"
  if [ "$CURRENT_UID" != "$TARGET_UID" ] || [ "$CURRENT_GID" != "$TARGET_GID" ] || [ "$CURRENT_HOME" != "$HOME_DIR" ]; then
    usermod -u "$TARGET_UID" -g "$TARGET_GID" -d "$HOME_DIR" -s /bin/bash "$USERNAME"
  fi
else
  install -d "$HOME_ROOT"
  useradd -m -u "$TARGET_UID" -g "$TARGET_GID" -d "$HOME_DIR" -s /bin/bash "$USERNAME"
fi

# Keep permissions scoped to the user's home directory.
install -d -m 700 -o "$USERNAME" -g "$GROUP_NAME" "$HOME_DIR"
install -d -m 700 -o "$USERNAME" -g "$GROUP_NAME" "$HOME_DIR/.ssh"

AUTH_FILE="$HOME_DIR/.ssh/authorized_keys"
LOCK_FILE="$HOME_DIR/.ssh/.authorized_keys.lock"
TMP_FILE="$(mktemp "$HOME_DIR/.ssh/authorized_keys.tmp.XXXXXX")"
cleanup_tmp_file() {{
  if [ -n "$TMP_FILE" ] && [ -e "$TMP_FILE" ]; then
    rm -f "$TMP_FILE"
  fi
}}
trap cleanup_tmp_file EXIT INT TERM HUP

(
  flock -x 9
  touch "$AUTH_FILE"
  chown "$USERNAME:$GROUP_NAME" "$AUTH_FILE"
  chmod 600 "$AUTH_FILE"

  if [ -n "$PAYLOAD_B64" ]; then
    printf '%s' "$PAYLOAD_B64" | base64 -d > "$TMP_FILE"
  else
    : > "$TMP_FILE"
  fi

  chown "$USERNAME:$GROUP_NAME" "$TMP_FILE"
  chmod 600 "$TMP_FILE"
  mv "$TMP_FILE" "$AUTH_FILE"
) 9>"$LOCK_FILE"
trap - EXIT INT TERM HUP
""".strip()
