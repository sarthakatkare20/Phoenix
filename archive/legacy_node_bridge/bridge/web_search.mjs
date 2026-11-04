/**
 * Live Web Search & Real-Time Intelligence Engine for J.A.R.V.I.S.
 * 
 * Provides live weather, Wikipedia instant facts, Google News RSS headlines,
 * and web summaries without requiring paid Search API quotas.
 */

/**
 * Fetch live weather from wttr.in
 */
export async function getLiveWeather(location = '') {
  try {
    const loc = encodeURIComponent(location.trim() || '')
    const res = await fetch(`https://wttr.in/${loc}?format=j1`, {
      headers: { 'User-Agent': 'curl/7.88.1' },
      signal: AbortSignal.timeout(4000),
    })
    if (!res.ok) return null
    const data = await res.json()
    const current = data.current_condition?.[0]
    const area = data.nearest_area?.[0]
    const city = area?.areaName?.[0]?.value || location || 'Current Location'
    const tempC = current?.temp_C || current?.FeelsLikeC
    const desc = current?.weatherDesc?.[0]?.value || 'Clear'
    const humidity = current?.humidity || '50'
    const wind = current?.windspeedKmph || '10'

    return {
      type: 'weather',
      city,
      tempC,
      desc,
      humidity,
      wind,
      summary: `Weather in ${city}: ${tempC}°C, ${desc}, humidity ${humidity}%, wind ${wind} km/h.`,
    }
  } catch (err) {
    console.warn('[jarvis:web_search] weather fetch failed:', err.message)
    return null
  }
}

/**
 * Fetch top news headlines from Google News RSS
 */
export async function getLiveNews(query = 'top news') {
  try {
    const q = encodeURIComponent(query.trim())
    const res = await fetch(
      `https://news.google.com/rss/search?q=${q}&hl=en-IN&gl=IN&ceid=IN:en`,
      {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' },
        signal: AbortSignal.timeout(5000),
      },
    )
    if (!res.ok) return null
    const xml = await res.text()
    const items = []
    const itemRegex = /<item>[\s\S]*?<title>([\s\S]*?)<\/title>[\s\S]*?<pubDate>([\s\S]*?)<\/pubDate>[\s\S]*?<\/item>/gi
    let match
    while ((match = itemRegex.exec(xml)) && items.length < 4) {
      const title = match[1].replace(/<!\[CDATA\[(.*?)\]\]>/g, '$1').trim()
      items.push(title)
    }
    if (items.length === 0) return null
    return {
      type: 'news',
      query,
      headlines: items,
      summary: `Latest headlines for "${query}":\n` + items.map((h, i) => `${i + 1}. ${h}`).join('\n'),
    }
  } catch (err) {
    console.warn('[jarvis:web_search] news fetch failed:', err.message)
    return null
  }
}

/**
 * Fetch Wikipedia summary for a topic
 */
export async function getWikiSummary(topic) {
  try {
    const cleanTopic = topic.replace(/^(who is|what is|tell me about|explain)\s+/i, '').trim()
    const res = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(cleanTopic)}`,
      {
        headers: { 'User-Agent': 'JarvisAssistant/1.0' },
        signal: AbortSignal.timeout(4000),
      },
    )
    if (!res.ok) return null
    const data = await res.json()
    if (data.extract) {
      return {
        type: 'wiki',
        title: data.title,
        extract: data.extract,
        summary: `${data.title}: ${data.extract}`,
      }
    }
  } catch (err) {
    console.warn('[jarvis:web_search] wiki fetch failed:', err.message)
  }
  return null
}

/**
 * Master web search coordinator:
 * Automatically determines if query is weather, news, or factual lookup.
 */
export async function liveWebSearch(query) {
  if (!query || typeof query !== 'string') return null
  const q = query.trim().toLowerCase()

  // 1. Weather
  if (/\b(?:weather|temperature|mausam|rain|forecast)\b/i.test(q)) {
    const cityMatch = q.match(/(?:in|of|at|for)\s+([a-zA-Z\s]+)/i)
    const city = cityMatch ? cityMatch[1].trim() : ''
    const weather = await getLiveWeather(city)
    if (weather) return weather.summary
  }

  // 2. News / Current Events / Stocks / Market
  if (/\b(?:news|headlines|latest update|today|nifty|sensex|stock market|cricket score|match)\b/i.test(q)) {
    const cleanQ = q.replace(/^(?:what is the|tell me|get|search)\s+/i, '')
    const news = await getLiveNews(cleanQ)
    if (news) return news.summary
  }

  // 3. Factual entity lookup
  if (/\b(?:who is|what is|tell me about)\b/i.test(q)) {
    const wiki = await getWikiSummary(q)
    if (wiki) return wiki.summary
  }

  // Fallback to news RSS search
  const generalNews = await getLiveNews(query)
  if (generalNews) return generalNews.summary

  return null
}
