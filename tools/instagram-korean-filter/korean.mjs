// Erkennung koreanischer Schriftzeichen (Hangul).
//
// Abgedeckt sind alle Unicode-Bloecke, in denen koreanische Schrift vorkommt --
// nicht nur die ueblichen Silbenbloecke (가-힣), sondern auch einzelne Jamo,
// halbbreite und eingekreiste Formen. Chinesische Han-Zeichen (Hanja) sind
// bewusst NICHT enthalten: sie kommen auch in japanischen und chinesischen
// Namen vor und waeren daher kein Hinweis auf einen koreanischen Account.

/** Unicode-Bloecke mit koreanischer Schrift, jeweils [von, bis]. */
export const KOREAN_BLOCKS = [
  ['ᄀ', 'ᇿ', 'Hangul Jamo'],
  ['㄰', '㆏', 'Hangul Compatibility Jamo'],
  ['㈀', '㈞', 'Eingeklammerte Hangul-Zeichen'],
  ['㉠', '㉾', 'Eingekreiste Hangul-Zeichen'],
  ['ꥠ', '꥿', 'Hangul Jamo Extended-A'],
  ['가', '힣', 'Hangul-Silben'],
  ['ힰ', '퟿', 'Hangul Jamo Extended-B'],
  ['ﾠ', 'ￜ', 'Halbbreite Hangul-Zeichen'],
];

const CLASS = KOREAN_BLOCKS.map(([from, to]) => `${from}-${to}`).join('');

/** Trifft auf ein einzelnes koreanisches Zeichen. */
export const KOREAN_CHAR = new RegExp(`[${CLASS}]`, 'u');

/** Trifft auf alle koreanischen Zeichen einer Zeichenkette. */
export const KOREAN_CHARS_GLOBAL = new RegExp(`[${CLASS}]`, 'gu');

/**
 * Normalisiert Text vor dem Vergleich. NFC fasst zerlegte Jamo wieder zu
 * Silben zusammen, damit "한" und "한" (dekomponiert) gleich behandelt werden.
 */
function normalize(text) {
  if (typeof text !== 'string' || text.length === 0) return '';
  try {
    return text.normalize('NFC');
  } catch {
    return text;
  }
}

/** true, wenn der Text mindestens ein koreanisches Zeichen enthaelt. */
export function containsKorean(text) {
  return KOREAN_CHAR.test(normalize(text));
}

/** Alle koreanischen Zeichen des Textes, ohne Wiederholungen, in Reihenfolge. */
export function koreanChars(text) {
  const found = normalize(text).match(KOREAN_CHARS_GLOBAL);
  return found ? [...new Set(found)] : [];
}

/** Anzahl der koreanischen Zeichen im Text (mit Wiederholungen). */
export function koreanCount(text) {
  const found = normalize(text).match(KOREAN_CHARS_GLOBAL);
  return found ? found.length : 0;
}

/**
 * Prueft mehrere Felder eines Accounts auf einmal.
 *
 * @param {Record<string, string|undefined>} fields z.B. { username, full_name }
 * @returns {{ matched: boolean, fields: string[], chars: string[] }}
 */
export function inspectFields(fields) {
  const matchedFields = [];
  const chars = new Set();
  for (const [name, value] of Object.entries(fields)) {
    const hits = koreanChars(value);
    if (hits.length > 0) {
      matchedFields.push(name);
      for (const char of hits) chars.add(char);
    }
  }
  return { matched: matchedFields.length > 0, fields: matchedFields, chars: [...chars] };
}
