/**
 * arabic.js — matching and inline decoration for Arabic page text.
 *
 * Two jobs:
 *  1. Build a search-highlight pattern that matches the way the backend
 *     matches. The FTS index is built on normalised text, so a search for
 *     `الهدايه` has to light up `الْهِدَايَة` on the page: diacritics are
 *     skippable and alef / ya / ta-marbuta variants are interchangeable.
 *  2. Mark up the quotations the source only signals with punctuation —
 *     Qur'anic ayat in brackets, hadith in quotes — so they can be set apart
 *     from the author's own words.
 */

const DIACRITICS = '[\\u064B-\\u065F\\u0610-\\u061A\\u06D6-\\u06DC\\u06DF-\\u06E4\\u06E7\\u06E8\\u06EA-\\u06ED\\u0640]*'
const ALEF = '\\u0622\\u0623\\u0625\\u0671\\u0627'
const YA = '\\u0649\\u064A'
const TA = '\\u0629\\u0647'

// The same sets as literal characters, for testing a single char.
const ALEF_CHARS = '\u0622\u0623\u0625\u0671\u0627'
const YA_CHARS = '\u0649\u064A'
const TA_CHARS = '\u0629\u0647'

const DIACRITIC_G = /[\u064B-\u0652\u0670]/g
const LETTER_G = /[\u0621-\u063A\u0641-\u064A]/g

function escapeRe(ch) {
  return ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function tolerantChar(ch) {
  if (ALEF_CHARS.includes(ch)) return `[${ALEF}]`
  if (YA_CHARS.includes(ch)) return `[${YA}]`
  if (TA_CHARS.includes(ch)) return `[${TA}]`
  return escapeRe(ch)
}

/**
 * A pattern that finds `query` in un-normalised page text.
 * Returns null for an empty query.
 */
export function buildMatchRegex(query) {
  const q = (query || '').trim()
  if (!q) return null
  const body = Array.from(q)
    .filter((c) => !/\s/.test(c))
    .map(tolerantChar)
    .join(DIACRITICS)
  if (!body) return null
  try {
    // Trailing vowels belong to the matched word — without this the
    // highlight would stop short and split `الرِّيَاحَ` mid-letter.
    return new RegExp(body + DIACRITICS, 'gi')
  } catch {
    return null
  }
}

export function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Escape for use as element content only. Quotation marks are left alone —
 * they are how the source marks a quoted hadith, and escaping them first
 * would hide that from the decorator below.
 */
function escapeText(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * Apply `regex` to the text of an HTML string, never inside a tag —
 * so decoration added earlier survives untouched.
 */
export function highlightHtml(html, regex) {
  if (!regex) return html
  return String(html)
    .split(/(<[^>]+>)/)
    .map((part) => {
      if (part.startsWith('<')) return part
      regex.lastIndex = 0
      return part.replace(regex, (m) => `<mark>${m}</mark>`)
    })
    .join('')
}

export function countMatches(text, regex) {
  if (!regex || !text) return 0
  regex.lastIndex = 0
  let n = 0
  while (regex.exec(text) !== null) {
    n++
    if (regex.lastIndex === 0) break
  }
  return n
}

// ── inline quotations ───────────────────────────────────────────────────────

function vowelRatio(s) {
  const letters = (s.match(LETTER_G) || []).length
  if (!letters) return 0
  return (s.match(DIACRITIC_G) || []).length / letters
}

// `(نص الآية)` optionally followed by `48 الروم` — 2,615 of these in the
// corpus. No `\b` after the surah name: JS word boundaries are ASCII-only
// and never fire at the end of an Arabic word.
const BRACKETED = /\(([^()]{8,400})\)(\s*\d{1,3}\s+[\u0621-\u064A]{3,})?/g
// `"متن الحديث"` — 3,541 in the corpus.
const QUOTED = /["“]([^"“”]{8,400})["”]/g

/**
 * Escape `text`, then mark up the quotations inside it.
 *
 * A bracketed passage counts as Qur'an when it is voweled the way the
 * mushaf is and runs to more than a couple of words; anything shorter is
 * an aside from the author and is left alone.
 */
export function decorateInline(text) {
  let html = escapeText(text)

  html = html.replace(QUOTED, (m, inner) => `<span class="q-hadith">${inner}</span>`)

  html = html.replace(BRACKETED, (m, inner, ref) => {
    const words = inner.trim().split(/\s+/).length
    if (words < 3 || vowelRatio(inner) < 0.3) return m
    const cite = ref ? `<span class="q-ref">${ref.trim()}</span>` : ''
    return `<span class="q-ayah">${inner.trim()}</span>${cite}`
  })

  return html
}

/** Escape + decorate + highlight, in the order that keeps tags intact. */
export function renderInline(text, regex) {
  return highlightHtml(decorateInline(text), regex)
}
