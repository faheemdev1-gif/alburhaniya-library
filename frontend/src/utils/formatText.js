/**
 * formatText.js — turns a raw page string from library.db into typed blocks
 * the reader can lay out properly.
 *
 * The shamela exports flatten every page into running text. Poetry survives
 * only as a `***` between the two hemistichs of a bayt, and consecutive bayts
 * — often with commentary running straight into them — sit on one line:
 *
 *   ‎…قال رضي الله عنه: صدر *** عجز (240 ق 2) ثم قال: صدر *** عجز…
 *
 * Rendering that as a paragraph is what makes these books hard to read.
 *
 * Finding where the verse starts and stops is the whole problem. The reliable
 * signal is vocalisation: in this corpus poetry is fully voweled (median
 * diacritic-to-letter ratio 0.75) while the surrounding commentary is bare
 * (median 0.00). So we classify each word, grow a verse span outward from
 * every `***`, and stop where the vowels stop. Inside a span the `***` marks
 * exact hemistich boundaries; where two bayts run together with no separator
 * between them, we cut on the bayt number if there is one and otherwise on
 * metre — hemistichs within a qasida are near-constant in length.
 *
 * Blocks returned by segmentPage():
 *   { type: 'bayt',    number, ref, sadr, ajuz }
 *   { type: 'para',    text }
 *   { type: 'heading', text }
 *   { type: 'quote',   text }
 *   { type: 'divider' }
 *   { type: 'folio',   text }
 */

// ── character classes ───────────────────────────────────────────────────────
const DIACRITIC = /[\u064B-\u0652\u0670]/g
const TATWEEL = /\u0640/g
const LETTER = /[\u0621-\u063A\u0641-\u064A]/g

// Exactly three asterisks separate the two hemistichs of a bayt (8,849 of
// them in the corpus). Four or more is a decorative section rule.
const SEP_TOKEN = '***'
const RULE_RE = /^(?:\*{4,}|\*{2,}[-–—_]{2,}[\s\S]*)$/
const RULE_SPLIT = /(\*{2,}[-–—_]{3,}\*{3}[-–—_]{3,}\*{2,}|\*{4,})/

// `419-` and `3 ق 1:` (bayt 3 of qasida 1) both head a bayt.
const BAYT_QAF_SRC = '\\d{1,4}\\s*(?:-\\s*\\d{1,4}\\s*)?ق\\s*\\d{1,3}'
const LEAD_QAF = new RegExp('^(' + BAYT_QAF_SRC + ')\\s*:\\s*')
const LEAD_NUM = /^(\d{1,4})\s*[-‑–ـ]\s*/
const BAYT_MARK = new RegExp('(?:(' + BAYT_QAF_SRC + ')\\s*:|(\\d{1,4})\\s*[-‑–ـ])\\s*', 'g')

// A bayt's own citation, e.g. `(240 ق 2)` or `(13 - 15 ق 57)`.
const TRAILING_REF = new RegExp('\\s*\\(\\s*' + BAYT_QAF_SRC + '\\s*\\)\\s*$')
const ANY_REF = new RegExp('^\\(\\s*' + BAYT_QAF_SRC + '\\s*\\)$')

// `-33-` on its own: the printed folio number left over from the scan.
const FOLIO_RE = /^[-‑–—]\s*(\d{1,4})\s*[-‑–—]$/

// Median hemistich in this corpus is 43 characters (n=1,270, σ≈8).
const DEFAULT_HEMISTICH = 43
// A word this voweled is almost certainly verse (or a quoted verse of Qur'an).
const VOCALISED = 0.35

const WS = /\s+/g
const clean = (s) => (s || '').replace(WS, ' ').trim()

function count(s, re) {
  const m = s.match(re)
  return m ? m.length : 0
}

/** Diacritics per letter, 0 when there is nothing to measure. */
function vowelRatio(word) {
  const letters = count(word, LETTER)
  if (!letters) return 0
  return count(word, DIACRITIC) / letters
}

/** Trim the punctuation a scribe would not have read aloud. */
function stripEdges(s) {
  return clean(s)
    .replace(/^[\s*\-–—_=~،,.:؛]+/, '')
    .replace(/[\s*\-–—_=~،,؛]+$/, '')
}

// ── word classification ─────────────────────────────────────────────────────

const VERSE = 1
const PROSE = -1
const NEUTRAL = 0

/**
 * Score one word as verse-like, prose-like, or neutral.
 *
 * Short function words (‎و، في، من، لا) carry no vowels either way, so they
 * stay neutral and inherit the run around them instead of breaking it.
 */
function classify(word) {
  const letters = count(word, LETTER)
  if (letters === 0) return NEUTRAL
  if (letters <= 2) return NEUTRAL
  return vowelRatio(word) >= VOCALISED ? VERSE : PROSE
}

/**
 * Hard stops: a verse span may never run through these.
 *  - `:`  an attribution — `قال رضي الله عنه:` — the verse begins after it
 *  - `""` quoted hadith
 *  - `()` a citation or a quoted ayah
 *
 * Parentheses need care: poets quote a single Qur'anic word inside a bayt
 * — `وَمَاتَ الْخَوْفُ عَنَّا حَيْثُ (إِنَّا)` — and treating that as a stop
 * would swallow the whole hemistich. So a bracketed group only counts as a
 * boundary when it is a real aside: two or more words, or a `ق` citation.
 */
function boundaryFlags(words) {
  const flags = words.map((w) => w !== SEP_TOKEN && /[:："“”«»]/.test(w))

  let open = -1
  for (let i = 0; i < words.length; i++) {
    if (words[i] === SEP_TOKEN) continue
    if (open < 0 && words[i].includes('(')) open = i
    if (open >= 0 && words[i].includes(')')) {
      const group = words.slice(open, i + 1)
      const aside = group.length >= 2 || /ق\s*\d/.test(group.join(' '))
      if (aside) for (let j = open; j <= i; j++) flags[j] = true
      open = -1
    }
  }
  // An unclosed bracket is a boundary on its own — the aside runs off the page.
  if (open >= 0) flags[open] = true
  return flags
}

// ── verse-span detection ────────────────────────────────────────────────────

/**
 * Given the words of a paragraph and the indices holding `***`, return the
 * maximal, merged spans of verse around them as [start, end) index pairs.
 */
function verseSpans(words) {
  const kinds = words.map((w) => (w === SEP_TOKEN ? VERSE : classify(w)))
  const bounds = boundaryFlags(words)
  const spans = []

  for (let i = 0; i < words.length; i++) {
    if (words[i] !== SEP_TOKEN) continue
    if (spans.length && spans[spans.length - 1][1] > i) continue

    // Walk out in both directions, tolerating single neutral words but
    // stopping at two prose words in a row, or at any hard boundary.
    let start = i
    let prose = 0
    for (let j = i - 1; j >= 0; j--) {
      if (bounds[j]) break
      if (kinds[j] === PROSE) {
        if (++prose >= 2) break
      } else if (kinds[j] === VERSE) {
        prose = 0
      }
      start = j
    }
    while (start < i && kinds[start] !== VERSE && words[start] !== SEP_TOKEN) start++

    let end = i + 1
    prose = 0
    for (let j = i + 1; j < words.length; j++) {
      if (bounds[j]) break
      if (kinds[j] === PROSE) {
        if (++prose >= 2) break
      } else if (kinds[j] === VERSE) {
        prose = 0
      }
      end = j + 1
    }
    while (end > i + 1 && kinds[end - 1] !== VERSE && words[end - 1] !== SEP_TOKEN) end--

    if (spans.length && start <= spans[spans.length - 1][1]) {
      spans[spans.length - 1][1] = Math.max(spans[spans.length - 1][1], end)
    } else {
      spans.push([start, end])
    }
  }
  return spans
}

// ── splitting a run of bayts ────────────────────────────────────────────────

/** Split at the word boundary whose left side lands closest to `target`. */
function splitNearLength(text, target) {
  const s = clean(text)
  if (!s) return ['', '']
  let best = -1
  let bestCost = Infinity
  const re = /\s+/g
  let m
  while ((m = re.exec(s)) !== null) {
    const cost = Math.abs(m.index - target)
    if (cost < bestCost) {
      bestCost = cost
      best = m.index
    }
  }
  if (best < 0) return [s, '']
  return [s.slice(0, best).trim(), s.slice(best).trim()]
}

/**
 * A chunk between two `***` holds the ajuz of one bayt then the sadr of the
 * next. A bayt number is an exact signal, so it wins; otherwise use metre.
 */
function splitMiddle(chunk, target) {
  const s = clean(chunk)
  BAYT_MARK.lastIndex = 0
  let m
  while ((m = BAYT_MARK.exec(s)) !== null) {
    if (m.index === 0) continue // belongs to the previous bayt's numbering
    const left = s.slice(0, m.index).trim()
    const right = s.slice(m.index + m[0].length).trim()
    if (left && right) return [left, right, (m[1] || m[2] || '').replace(WS, ' ').trim()]
    break
  }
  const [left, right] = splitNearLength(s, target)
  return [left, right, null]
}

function takeLeadingNumber(text) {
  const s = clean(text)
  const qaf = s.match(LEAD_QAF)
  if (qaf) return [qaf[1].replace(WS, ' ').trim(), s.slice(qaf[0].length).trim()]
  const num = s.match(LEAD_NUM)
  if (num) return [num[1], s.slice(num[0].length).trim()]
  return [null, s]
}

function takeTrailingRef(text) {
  const s = clean(text)
  const m = s.match(TRAILING_REF)
  if (!m) return [null, s]
  return [m[0].trim().replace(/^\(|\)$/g, '').replace(WS, ' ').trim(), s.slice(0, m.index).trim()]
}

/** Turn one verse span (already free of surrounding prose) into bayts. */
function spanToBayts(spanText) {
  const chunks = clean(spanText).split(SEP_TOKEN).map((c) => c.trim())
  const k = chunks.length - 1
  if (k < 1) return []

  const middles = chunks.slice(1, -1).filter(Boolean)
  const target = middles.length
    ? middles.reduce((a, c) => a + c.length, 0) / middles.length / 2
    : DEFAULT_HEMISTICH

  const halves = [chunks[0]]
  const markers = new Array(k).fill(null)
  for (let i = 1; i < k; i++) {
    const [left, right, marker] = splitMiddle(chunks[i], target)
    halves.push(left, right)
    if (marker) markers[i] = marker
  }
  halves.push(chunks[k])

  const bayts = []
  for (let i = 0; i < k; i++) {
    let sadr = halves[i * 2] || ''
    let ajuz = halves[i * 2 + 1] || ''
    let number = markers[i]

    const [leadNum, rest] = takeLeadingNumber(sadr)
    if (leadNum) {
      number = number || leadNum
      sadr = rest
    }
    let ref = null
    ;[ref, ajuz] = takeTrailingRef(ajuz)

    sadr = stripEdges(sadr)
    ajuz = stripEdges(ajuz)
    if (!sadr && !ajuz) continue
    bayts.push({ type: 'bayt', number: number || null, ref: ref || null, sadr, ajuz })
  }
  return bayts
}

// ── prose ───────────────────────────────────────────────────────────────────

const LEAD_LABEL =
  /^(المعنى|المعني|الشرح|شرح المفردات|المفردات|اللغة|الإعراب|المناسبة|ملحوظة|ملاحظة|فائدة|تنبيه)\s*:\s*/

function isHeading(s) {
  if (s.length > 70) return false
  if (/[.؟!]$/.test(s)) return false
  if (/^(باب|فصل|مقدمة|خاتمة|تمهيد|القصيدة|قصيدة|الوصية|خطاب|وصية)\b/.test(s)) return true
  // A trailing colon only makes a heading out of a short, comma-free label —
  // otherwise it is just a sentence introducing what comes next.
  if (/:$/.test(s) && s.length <= 50 && !/[,،؛]/.test(s)) return true
  return false
}

const STANDALONE_QUOTE = /^["“«]([\s\S]{8,})["”»]$/
// A bayt marker left alone on its line — `53 ق 1:` — belongs to the next bayt.
const LONE_MARKER = new RegExp('^(?:(' + BAYT_QAF_SRC + ')\\s*:|(\\d{1,4})\\s*[-‑–ـ])$')
// An orphaned citation that drifted to the head of a gloss.
const LEADING_REF = new RegExp('^\\(\\s*' + BAYT_QAF_SRC + '\\s*\\)\\s*')

function proseBlocks(text) {
  const raw = clean(text)
  if (!raw) return []

  // Match the folio first: stripEdges would eat the dashes that identify it.
  const folio = raw.match(FOLIO_RE)
  if (folio) return [{ type: 'folio', text: folio[1] }]
  if (RULE_RE.test(raw)) return [{ type: 'divider' }]

  // Likewise a bare bayt marker (`13-`, `53 ق 1:`) — the trailing dash or
  // colon is what identifies it, and stripEdges would remove it.
  const lone = raw.match(LONE_MARKER)
  if (lone) return [{ type: 'marker', text: (lone[1] || lone[2]).replace(WS, ' ').trim() }]

  let s = stripEdges(raw)
  if (!s) return []
  if (ANY_REF.test(s)) return [] // `(240 ق 2)` — already carried on its bayt

  s = s.replace(LEADING_REF, '').trim()
  if (!s) return []

  const quoted = s.match(STANDALONE_QUOTE)
  if (quoted && !/["“«]/.test(quoted[1])) return [{ type: 'quote', text: quoted[1].trim() }]

  // `المعني: …` opens the commentary. Peel the label off first so a short
  // gloss does not get mistaken for a heading in its entirety.
  const label = s.match(LEAD_LABEL)
  if (label) {
    const rest = s.slice(label[0].length).trim()
    if (!rest) return [{ type: 'heading', text: label[1] }]
    return [
      { type: 'heading', text: label[1] },
      { type: 'para', text: rest },
    ]
  }

  if (isHeading(s)) return [{ type: 'heading', text: s }]
  return [{ type: 'para', text: s }]
}

// ── entry point ─────────────────────────────────────────────────────────────

function segmentParagraph(paragraph, out) {
  if (!paragraph.includes(SEP_TOKEN)) {
    out.push(...proseBlocks(paragraph))
    return
  }

  const words = paragraph.split(' ').filter(Boolean)
  const spans = verseSpans(words)
  if (!spans.length) {
    out.push(...proseBlocks(paragraph.split(SEP_TOKEN).join(' ')))
    return
  }

  let cursor = 0
  for (const [start, end] of spans) {
    if (start > cursor) out.push(...proseBlocks(words.slice(cursor, start).join(' ')))
    const bayts = spanToBayts(words.slice(start, end).join(' '))
    if (bayts.length) out.push(...bayts)
    else out.push(...proseBlocks(words.slice(start, end).join(' ').split(SEP_TOKEN).join(' ')))
    cursor = end
  }
  if (cursor < words.length) out.push(...proseBlocks(words.slice(cursor).join(' ')))
}

/**
 * @param {string} raw page text as stored in library.db
 * @returns {Array} typed blocks
 */
export function segmentPage(raw) {
  if (!raw) return []
  const blocks = []

  for (const rawParagraph of String(raw).split(/\n{2,}/)) {
    const paragraph = clean(rawParagraph)
    if (!paragraph) continue

    // Peel off decorative rules FIRST — they are often glued to real text
    // (`… **----***----** -33-`) and they contain a `***` of their own, which
    // would otherwise be mistaken for a hemistich separator.
    for (const part of paragraph.split(RULE_SPLIT)) {
      const piece = clean(part)
      if (!piece) continue
      if (/^(?:\*{4,}|\*{2,}[-–—_])/.test(piece)) {
        if (blocks.length && blocks[blocks.length - 1].type !== 'divider') {
          blocks.push({ type: 'divider' })
        }
        continue
      }
      // Now give each separator its own token, so word indices stay meaningful.
      segmentParagraph(piece.replace(/(?<!\*)\*{3}(?!\*)/g, ' ' + SEP_TOKEN + ' '), blocks)
    }
  }

  // A marker that arrived on its own line numbers the bayt that follows it.
  const folded = []
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i]
    if (b.type !== 'marker') {
      folded.push(b)
      continue
    }
    const next = blocks[i + 1]
    if (next && next.type === 'bayt') {
      next.number = next.number || b.text
    } else {
      folded.push({ type: 'heading', text: b.text })
    }
  }

  while (folded.length && folded[0].type === 'divider') folded.shift()
  while (folded.length && folded[folded.length - 1].type === 'divider') folded.pop()
  return folded
}

export default segmentPage
