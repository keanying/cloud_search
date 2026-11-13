// 图表：按需加载 ECharts（仅注册用到的图表与组件，单独成包，不影响首屏）
export interface ChartSpec {
  type: 'bar' | 'line' | 'pie'
  title: string
  unit: string | null
  categories: string[]
  series: { name: string; values: (number | null)[] }[]
  source: string | null
}

/** 校验 ```chart 代码块中的 JSON；不合法返回 null（界面显示原文） */
export function parseChartSpec(raw: string): ChartSpec | null {
  try {
    const o = JSON.parse(raw)
    if (!o || !['bar', 'line', 'pie'].includes(o.type)) return null
    if (!Array.isArray(o.categories) || !Array.isArray(o.series) || !o.series.length) return null
    const series = o.series
      .filter((s: unknown) => s && typeof s === 'object' && Array.isArray((s as { values?: unknown }).values))
      .map((s: { name?: unknown; values: unknown[] }) => ({
        name: String(s.name ?? ''),
        values: s.values.map((v) => (typeof v === 'number' && Number.isFinite(v) ? v : null)),
      }))
    if (!series.length) return null
    return {
      type: o.type,
      title: String(o.title ?? ''),
      unit: o.unit ? String(o.unit) : null,
      categories: o.categories.map((c: unknown) => String(c)),
      series,
      source: o.source ? String(o.source) : null,
    }
  } catch {
    return null
  }
}

export async function loadECharts() {
  return (await import('./echarts-setup')).echarts
}

// 与界面粉彩卡片同色系（饱和一档，保证图表可读）
const PALETTE = ['#3d8bd4', '#2bb27a', '#7b68d8', '#e0a400', '#e46a3a', '#4fb3bf', '#b35fb0', '#8a8d93']
const PALETTE_DARK = ['#7ab4e8', '#5fcf9a', '#a596ef', '#ebc85a', '#f19a7c', '#7fd0da', '#d39ad0', '#b0b2b8']

export function buildOption(spec: ChartSpec, dark: boolean) {
  const text = dark ? '#dcdcd6' : '#303236'
  const muted = dark ? '#8a8a85' : '#8a8c92'
  const line = dark ? 'rgba(255,255,255,.08)' : 'rgba(17,18,20,.08)'
  const unit = spec.unit ? ` ${spec.unit}` : ''
  const fmt = (v: unknown) => (v == null ? '无数据' : `${typeof v === 'number' ? v.toLocaleString('zh-CN') : v}${unit}`)
  const base = {
    color: dark ? PALETTE_DARK : PALETTE,
    backgroundColor: 'transparent',
    textStyle: { color: text, fontFamily: 'inherit' },
    title: { text: spec.title, left: 'center', top: 4, textStyle: { color: text, fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: spec.type === 'pie' ? 'item' : 'axis', valueFormatter: fmt },
    legend: { show: spec.series.length > 1 || spec.type === 'pie', bottom: 0, textStyle: { color: text } },
  }
  if (spec.type === 'pie') {
    const s = spec.series[0]
    return {
      ...base,
      series: [{
        type: 'pie', radius: ['38%', '66%'], center: ['50%', '52%'], itemStyle: { borderRadius: 6, borderColor: dark ? '#1f1f22' : '#fff', borderWidth: 2 },
        label: { color: text, formatter: '{b}\n{d}%' },
        data: spec.categories.map((c, i) => ({ name: c, value: s.values[i] })),
      }],
    }
  }
  return {
    ...base,
    grid: { left: 12, right: 16, top: 44, bottom: spec.series.length > 1 ? 36 : 12, containLabel: true },
    xAxis: { type: 'category', data: spec.categories, axisLine: { lineStyle: { color: line } }, axisLabel: { color: muted, interval: 0, hideOverlap: true } },
    yAxis: { type: 'value', name: spec.unit ?? '', nameTextStyle: { color: muted }, splitLine: { lineStyle: { color: line } }, axisLabel: { color: muted } },
    series: spec.series.map((s) => ({
      name: s.name, type: spec.type, data: s.values, smooth: spec.type === 'line', barMaxWidth: 36,
      itemStyle: spec.type === 'bar' ? { borderRadius: [10, 10, 0, 0] } : undefined,
      connectNulls: false,
    })),
  }
}
