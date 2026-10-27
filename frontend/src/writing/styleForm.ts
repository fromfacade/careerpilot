export function phrasesToText(phrases: string[]): string {
  return phrases.join('\n')
}

export function textToPhrases(text: string): string[] {
  const seen = new Set<string>()
  const phrases: string[] = []
  for (const line of text.split('\n')) {
    const phrase = line.trim()
    if (!phrase) continue
    const key = phrase.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    phrases.push(phrase)
  }
  return phrases
}
