#!/usr/bin/env bash
# 把「可上架技能」打包成 WorkBuddy 上传用的 zip。
#
#   bash workbuddy/pack.sh
#
# 产物：
#   workbuddy/dist/<slug>/          目录形态（有些平台直接拖文件夹）
#   workbuddy/dist/<slug>.zip       zip 形态，内含 <slug>/SKILL.md
#
# 只打包 UPLOAD_SET 里的技能——另外两个技能依赖 Claude Code 运行时，不上架（见 README.md）。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/workbuddy/dist"

UPLOAD_SET=(smart-loop tech-reserve-finder)

rm -rf "$DIST"
mkdir -p "$DIST"

for slug in "${UPLOAD_SET[@]}"; do
  src="$ROOT/tools/$slug"
  [ -f "$src/SKILL.md" ] || { echo "缺少 $src/SKILL.md，中止"; exit 1; }

  # 用 rsync 风格的目录镜像：保留 SKILL.md 与 references/ / scripts/ / templates/
  mkdir -p "$DIST/$slug"
  cp "$src/SKILL.md" "$DIST/$slug/SKILL.md"
  for sub in references scripts templates; do
    if [ -d "$src/$sub" ]; then
      cp -r "$src/$sub" "$DIST/$slug/$sub"
    fi
  done

  # 用 python 打 zip（Git Bash 通常没有 zip 命令）
  python - "$DIST" "$slug" <<'PY'
import sys, os, zipfile
dist, slug = sys.argv[1], sys.argv[2]
src = os.path.join(dist, slug)
out = os.path.join(dist, slug + ".zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        for name in sorted(files):
            full = os.path.join(root, name)
            arc = os.path.relpath(full, src)
            z.write(full, arcname=f"{slug}/{arc}")
print(f"  {slug}.zip  ({os.path.getsize(out)} bytes)  {len(os.listdir(src))} files at root")
PY
done

echo
echo "打包完成 → $DIST"
echo "上传前请先核对：skill 名 = 目录名、allowed-tools 用逗号分隔、正文 ≤500 行。"
