# Amazon OCR Comparison - B0G39C97WQ

This file compares three extraction modes for the same Amazon product page.
The existing default preview and no-OCR probe files are preserved.

## Files
- Default extraction: `amazon_extract_preview_B0G39C97WQ.md`
- No-OCR DOM/alt probe: `amazon_no_ocr_dom_probe_B0G39C97WQ.md`
- OCR raw text from screenshot: `amazon_ocr_raw_screenshot_B0G39C97WQ.txt`

## Experiment Conditions
- Run at: 2026-05-01 13:19:49
- OCR engine: Windows.Media.Ocr Japanese recognizer
- OCR target: `C:/Users/mahha/Pictures/Screenshots/????????? 2026-05-01 130320.png`
- OCR scope: one visible carousel screenshot, not all carousel pages yet
- Chrome extension projection: repeat this screenshot OCR for every carousel/tab state, then merge/dedupe with DOM text

## Size / Coverage Comparison
| Mode | Characters | Sections | Bullet/extracted lines | Notes |
|---|---:|---:|---:|---|
| Default extraction | 3400 | 5 | 33 | Product metadata, product bullets, description, specs |
| No-OCR DOM/alt probe | 7442 | 9 | 311 | Adds hidden A+ DOM text, image alt/title/aria labels, comparison-table text |
| OCR screenshot sample | raw 532, compact 267 | 1 OCR block | 2 detected chunks | Adds image-baked visible labels/headline/body from the screenshot |

## Does The OCR Screenshot Text Already Exist?
- Full compact OCR text exists in default extraction: False
- Full compact OCR text exists in no-OCR DOM/alt probe: False
- OCR chunks absent from no-OCR DOM/alt probe: 2 / 2

## OCR Raw Text
```text
コ ン バ ク ト & 調 整 可 能 マ グ ネ テ ィ ッ ク カ バ - [ 2 ] し つ か り 装 着 ク リ ッ プ 式 つ 外 し & マ イ ク の ー マ グ ネ テ ィ ッ ク ク リ ッ プ ア - テ ィ ス ト カ バ - オ - ル イ ン ワ ン 収 納 [ 11 ] コ ン ハ ク ト で 自 由 な 角 度 調 整 が 可 能 わ ず か 11 9 い ] の ト ラ ン ス ミ ッ タ ー は 、 マ グ ネ ッ ト 着 脱 式 と ク リ ッ プ 着 脱 式 の 両 方 に 対 応 し 、 取 り 外 し 可 能 で ア ッ プ グ レ ー ド さ れ 、 マ イ ク の 向 き を 調 整 で き る マ グ ネ テ ィ ッ ク ク リ ッ プ に よ り 、 柔 軟 な 角 度 調 整 と 正 確 な 集 音 が 可 能 で す 。 ・ マ グ ネ ッ ト 式 強 力 固 定 3 音 声 ト - ン プ リ セ ッ ト [ 5 ] 細 部 に こ だ わ っ た 豊 か な サ ウ ン ド ノ イ ズ キ ャ ン セ リ ン グ [ 8 ] 音 割 れ の な い オ - デ ィ オ ゲ イ ン 調 整
```

## OCR Compact Text
```text
コンバクト&調整可能マグネティックカバ-[2]しつかり装着クリップ式つ外し&マイクのーマグネティッククリップア-ティストカバ-オ-ルインワン収納[11]コンハクトで自由な角度調整が可能わずか119い]のトランスミッターは、マグネット着脱式とクリップ着脱式の両方に対応し、取り外し可能でアップグレードされ、マイクの向きを調整できるマグネティッククリップにより、柔軟な角度調整と正確な集音が可能です。・マグネット式強力固定3音声ト-ンプリセット[5]細部にこだわった豊かなサウンドノイズキャンセリング[8]音割れのないオ-ディオゲイン調整
```

## OCR Human-Readable Postprocess Target
OCR raw output is useful, but it needs lightweight normalization. A corrected version of this screenshot would be:

```md
## A+ Carousel OCR Text
- コンパクト&調整可能
- マグネティックカバー[2]
- クリップ式 しっかり装着
- マグネット式 強力固定
- マグネティッククリップ 取り外し&マイクの向きを調整可能
- アーティストカバー
- オールインワン収納[11]
- コンパクトで自由な角度調整が可能
- わずか11 g[1]のトランスミッターは、マグネット着脱式とクリップ着脱式の両方に対応し、取り外し可能でアップグレードされ、マイクの向きを調整できるマグネティッククリップにより、柔軟な角度調整と正確な集音が可能です。
- 3音声トーンプリセット[5]
- 細部にこだわった豊かなサウンド
- ノイズキャンセリング[8]
- 音割れのないオーディオ
- ゲイン調整
```

## OCR Chunks Not Found In No-OCR Probe
- コンバクト&調整可能マグネティックカバ-[2]しつかり装着クリップ式つ外し&マイクのーマグネティッククリップア-ティストカバ-オ-ルインワン収納[11]コンハクトで自由な角度調整が可能わずか119い]のトランスミッターは、マグネット着脱式とクリップ着脱式の両方に対応し、取り外し可能でアップグレードされ、マイクの向きを調整できるマグネティッククリップにより、柔軟な角度調整と正確な集音が可能です
- マグネット式強力固定3音声ト-ンプリセット[5]細部にこだわった豊かなサウンドノイズキャンセリング[8]音割れのないオ-ディオゲイン調整

## What Changes In Markdown If OCR Is Added?
A Chrome-extension OCR pass would add a new section like this for each captured carousel page:

```md
## A+ Carousel OCR Text
- コンバクト&調整可能マグネティックカバ-[2]しつかり装着クリップ式つ外し&マイクのーマグネティッククリップア-ティストカバ-オ-ルインワン収納[11]コンハクトで自由な角度調整が可能わずか119い]のトランスミッターは、マグネット着脱式とクリップ着脱式の両方に対応し、取り外し可能でアップグレードされ、マイクの向きを調整できるマグネティッククリップにより、柔軟な角度調整と正確な集音が可能です。・マグネット式強力固定3音声ト-ンプリセット[5]細部にこだわった豊かなサウンドノイズキャンセリング[8]音割れのないオ-ディオゲイン調整
```

## Judgment
- Default extraction is useful but misses some A+ visual text.
- No-OCR DOM/alt extraction adds many carousel/tab/comparison labels, but still cannot guarantee text baked into images.
- OCR clearly recovers visible image text from the screenshot, including the large headline/body and small overlay labels.
- For PC Chrome extension flow, OCR should be an optional enhancement after DOM extraction.
- For smartphone/server flow, keep server-side Apify candidates plus HTML fallback. Server-side OCR requires rendering screenshots reliably, so it should remain secondary.
