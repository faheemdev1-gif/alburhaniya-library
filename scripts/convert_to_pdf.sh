#!/usr/bin/env bash
#
# convert_to_pdf.sh — Batch-convert DOCX/DOC/HTML/HTM/TXT/ODT files to PDF
# using LibreOffice headless mode. Arabic-safe (preserves RTL text).
#
# Usage:
#   ./convert_to_pdf.sh <input_dir> [output_dir]
#
# Example:
#   ./convert_to_pdf.sh ./books ./books_pdf
#
# If output_dir is omitted, converted PDFs are placed in <input_dir>/pdf_output
#
# Requires: LibreOffice (soffice) installed.
#   Ubuntu/Debian: sudo apt install libreoffice
#   macOS:         brew install --cask libreoffice
#   Windows:       install LibreOffice, run this script via WSL or Git Bash
#
set -euo pipefail

# ── Args ──────────────────────────────────────────────────────────────────────
INPUT_DIR="${1:-}"
OUTPUT_DIR="${2:-}"

if [[ -z "$INPUT_DIR" ]]; then
  echo "Usage: $0 <input_dir> [output_dir]"
  echo "Example: $0 ./books ./books_pdf"
  exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "Error: input directory '$INPUT_DIR' does not exist."
  exit 1
fi

if [[ -z "$OUTPUT_DIR" ]]; then
  OUTPUT_DIR="${INPUT_DIR%/}/pdf_output"
fi
mkdir -p "$OUTPUT_DIR"

# ── Find soffice binary ─────────────────────────────────────────────────────
SOFFICE_BIN=""
for candidate in soffice libreoffice "/Applications/LibreOffice.app/Contents/MacOS/soffice"; do
  if command -v "$candidate" >/dev/null 2>&1; then
    SOFFICE_BIN="$candidate"
    break
  elif [[ -x "$candidate" ]]; then
    SOFFICE_BIN="$candidate"
    break
  fi
done

if [[ -z "$SOFFICE_BIN" ]]; then
  echo "Error: LibreOffice (soffice) not found in PATH."
  echo "Install it first:"
  echo "  Ubuntu/Debian: sudo apt install libreoffice"
  echo "  macOS:         brew install --cask libreoffice"
  exit 1
fi

echo "Using LibreOffice: $SOFFICE_BIN"
echo "Input directory:   $INPUT_DIR"
echo "Output directory:  $OUTPUT_DIR"
echo ""

# ── Supported source extensions ─────────────────────────────────────────────
EXTENSIONS=("docx" "doc" "odt" "html" "htm" "rtf")

# ── Build file list ──────────────────────────────────────────────────────────
FILES=()
while IFS= read -r -d '' f; do
  FILES+=("$f")
done < <(
  find "$INPUT_DIR" -maxdepth 1 -type f \( \
    -iname "*.docx" -o -iname "*.doc" -o -iname "*.odt" \
    -o -iname "*.html" -o -iname "*.htm" -o -iname "*.rtf" \
  \) -print0
)

TOTAL=${#FILES[@]}
if [[ "$TOTAL" -eq 0 ]]; then
  echo "No convertible files found in '$INPUT_DIR'."
  echo "(Looking for: ${EXTENSIONS[*]})"
  exit 0
fi

echo "Found $TOTAL file(s) to convert."
echo ""

# ── Convert ───────────────────────────────────────────────────────────────────
SUCCESS=0
FAILED=0
FAILED_FILES=()

# Use a dedicated user profile dir to avoid clashing with any running LO instance
# and to allow safe parallel/sequential runs.
PROFILE_DIR=$(mktemp -d)
trap 'rm -rf "$PROFILE_DIR"' EXIT

# Track output stems we've already used so we never silently overwrite a
# previous conversion (e.g. "book.docx" and "book.html" would otherwise both
# produce "book.pdf" and one would clobber the other).
# NOTE: using a plain array instead of `declare -A` for compatibility with
# macOS's default bash 3.2 (which has no associative arrays).
USED_STEMS=()

stem_already_used() {
  local target="$1"
  local s
  for s in "${USED_STEMS[@]:-}"; do
    [[ "$s" == "$target" ]] && return 0
  done
  return 1
}

for i in "${!FILES[@]}"; do
  f="${FILES[$i]}"
  name=$(basename "$f")
  ext="${name##*.}"
  base="${name%.*}"
  num=$((i + 1))
  printf "[%d/%d] Converting: %s ... " "$num" "$TOTAL" "$name"

  # Convert into an isolated temp dir first, so we control the final filename
  # ourselves rather than trusting LibreOffice's output naming.
  CONV_TMP=$(mktemp -d)

  if "$SOFFICE_BIN" \
      -env:UserInstallation="file://$PROFILE_DIR" \
      --headless --norestore --convert-to pdf \
      --outdir "$CONV_TMP" "$f" \
      > /tmp/soffice_convert.log 2>&1; then

    produced=$(find "$CONV_TMP" -maxdepth 1 -iname "*.pdf" | head -n1)

    if [[ -n "$produced" ]]; then
      # Determine a collision-safe final name: base.pdf, or base (ext).pdf
      # if another source file already produced base.pdf.
      final_name="$base.pdf"
      if stem_already_used "$base"; then
        final_name="$base ($ext).pdf"
      fi
      USED_STEMS+=("$base")

      mv "$produced" "$OUTPUT_DIR/$final_name"
      echo "✓  →  $final_name"
      SUCCESS=$((SUCCESS + 1))
    else
      echo "✗ (no output file produced)"
      FAILED=$((FAILED + 1))
      FAILED_FILES+=("$name")
    fi
  else
    echo "✗ (conversion error)"
    FAILED=$((FAILED + 1))
    FAILED_FILES+=("$name")
  fi

  rm -rf "$CONV_TMP"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────"
echo "Done. $SUCCESS succeeded, $FAILED failed (of $TOTAL)."
echo "PDFs saved to: $OUTPUT_DIR"

if [[ "$FAILED" -gt 0 ]]; then
  echo ""
  echo "Failed files:"
  for ff in "${FAILED_FILES[@]}"; do
    echo "  - $ff"
  done
  echo ""
  echo "See /tmp/soffice_convert.log for the last error detail."
fi

echo ""
echo "Note: .txt files are not converted (the search system reads .txt directly)."
echo "Note: .pdf files are already in the right format and were skipped."
