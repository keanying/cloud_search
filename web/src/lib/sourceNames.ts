/** 来源标题与站点名整理，与后端 search/source_names.py 规则一致（旧数据在前端也能显示干净）：
 *  去掉标题末尾的站点后缀（“…_腾讯新闻”“… - 新浪财经”），丢弃版权声明等无效站点名，取不到时用域名。 */
const BAD_SITE = /copyright|©|all rights reserved|版权所有|icp|备案|powered by|\d{4}\s*[-–]\s*\d{4}/i
const SEP = /\s*(?:_|\||｜|——|—)\s*|\s+[-–]\s+/
const SHORT_NAME = /^[一-鿿A-Za-z0-9. ]{2,12}$/
const DOMAIN = /^[a-z0-9.-]+\.[a-z]{2,}$/i

export function hostName(url: string | null | undefined): string {
  try {
    return new URL(url || '').hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}

function validSite(name: string | null | undefined): string | null {
  const n = (name || '').replace(/\s+/g, ' ').trim()
  if (!n || n.length > 20 || BAD_SITE.test(n) || n.includes('://')) return null
  return n
}

export function tidySource(title: string | null | undefined, siteName: string | null | undefined, url: string | null | undefined) {
  let site = validSite(siteName)
  let t = (title || '').replace(/\s+/g, ' ').trim()
  if (/^[0-9a-f]{16,}(\.pdf)?$/i.test(t)) t = '' // 文件名是哈希（如 PDF），不当作标题
  for (let i = 0; i < 2; i++) {
    const parts = t.split(SEP)
    if (parts.length < 2) break
    const tail = parts[parts.length - 1].trim()
    const head = t.slice(0, t.length - tail.length).replace(/[\s_|｜\-–—]+$/, '')
    if (!tail || !head || head.length < 6) break
    const same = !!site && (tail.toLowerCase() === site.toLowerCase() || site.includes(tail) || tail.includes(site))
    if (!same) {
      if (tail.length > 12 || !SHORT_NAME.test(tail)) break
      if (site && !DOMAIN.test(site) && !DOMAIN.test(tail)) {
        t = head
        continue
      }
      site = !site || DOMAIN.test(site) ? tail : site
    }
    t = head
  }
  return { title: t || null, site: site || hostName(url) || '未知来源', host: hostName(url) }
}
