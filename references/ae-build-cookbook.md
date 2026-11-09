# AE ExtendScript 构建手册

`gen_build.mjs` 生成一个巨大的 `.jsx`，在 AE 里执行后产出可编辑工程。
本文是那套构建代码的规范与函数库说明。

## 构建脚本的整体骨架

```jsx
// 1. 数据（由 gen_build.mjs 用 JSON.stringify 注入，约 10 万行）
var DATA = { /* data.json 全量 */ };
var FONTPS = "ZCOOLXiaoWei-Regular";
var OUTAEP = "…/xxx_AE.aep";
var LOG = [];

// 2. 清空当前工程（危险：跑之前必须存盘）
while (app.project.numItems > 0) { try { app.project.item(1).remove(); } catch(e){ break; } }

// 3. 建主合成
var comp = app.project.items.addComp("MAIN", 1920, 1080, 1, DATA.dur, DATA.fps);

// 4. 函数库（见下）
// 5. 逐块建层（ENV/CAM → 场景 → 道具 → 粒子 → 歌词 → 后期）
// 6. 保存 + 写日志
try { app.project.save(new File(OUTAEP)); say("已保存"); } catch(e) { say("保存失败:" + e); }
flushLog();
```

**必须先存盘再跑。** 第 2 步会删掉当前工程所有 item。

## 十二个核心函数

| 函数 | 作用 | 备注 |
|---|---|---|
| `say(s)` | 写日志到数组 | AE 脚本没有 console，日志必须先攒起来最后落盘 |
| `flushLog(extra)` | 把 LOG 写进 `_buildlog.txt` | UTF-8，出问题第一时间看这个文件 |
| `shLayer(name)` | 新建形状层并命名 | `comp.layers.addShape()` |
| `grp(l,name,pts,closed,color,op,sw,scol)` | 往形状层里加一个"组 + 路径 + 填充 + 可选描边" | `pts` 是 `[[x,y],…]` |
| `ell(l,name,ctr,size,color,op)` | 椭圆组 | `size` 是 `[w,h]`，`ctr` 是 `[x,y]` |
| `addFeatherMask(l,pts,feather)` | 加蒙版并羽化 | 需兼容两种 matchName，见下 |
| `setKeys(prop,keys)` | 批量打关键帧 `[[t,v],…]` | `t` 单位是**秒**，不是帧 |
| `addSlider(layer,name,keys)` | 加滑块控制 + 打关键帧 | 控制器的基本单元 |
| `colorExprLayer(l,colorKeys)` | 给填充色打颜色关键帧 | |
| `anchorLayer(l,ax,ay,d)` | 视差锚定：anchor 定在对象自身上，position/scale 走表达式读 CAM | `d` 是视差深度，0=不跟随，1=完全跟随 |
| `opExpr / posExpr / rotExpr` | 写表达式（自动拼 PRELUDE） | |
| `masterCol(name)` | 返回"母色层填充色"的表达式路径字符串 | 一处改色，全局联动 |

## 表达式前奏 PRELUDE

每个表达式都会拼上这段，提供常用函数：

```js
function E(s){ return thisComp.layer('ENV').effect(s)('ADBE Slider Control-0001'); }
function sw4(s){ /* 4 个季节的平滑权重，返回 [w0,w1,w2,w3] */ }
function CAM(){ var c = thisComp.layer('CAM').transform.position; return [c[0], c[1]]; }
function ZM(){ return thisComp.layer('CAM').effect('ZOOM')('ADBE Slider Control-0001'); }
function camP(ax,ay,d){ /* 把对象坐标按 CAM 位置与 ZOOM、按深度 d 折算成屏幕坐标 */ }
function camS(d){ return (1 + (ZM()-1)*d) * 100; }
function LP(a,b,k){ return a + (b-a)*k; }          // 数值插值
function MC(a,b,k){ return [LP(a[0],b[0],k), LP(a[1],b[1],k), LP(a[2],b[2],k)]; }  // 颜色插值
```

表达式里**只允许写一行映射**，例如：

```js
camL.transform.opacity.expression = ex("return E('Sunset')*13;");
```

不要在表达式里做循环、数组运算、多步插值——那应该已经在 Node 侧算成关键帧了。

## 两个引导层：ENV 与 CAM

```jsx
var envL = comp.layers.addNull(); envL.name = "ENV"; envL.guideLayer = true;
var camL = comp.layers.addNull(); camL.name = "CAM"; camL.guideLayer = true;
```

- `guideLayer = true` 让它**不参与渲染**，但表达式仍能读到它的属性
- `ENV` 上挂一组滑块：Season / Daylight / Sunset / Wind / LeafAmt / SnowAmt / PetalAmt / FireflyAmt / LightSpot / Letter / Kite / Photo / Silhouette…
- `CAM` 用 Position 关键帧做运镜路径，另加一个 `ZOOM` 滑块做推拉
- 所有场景层的 `anchorLayer(l, ax, ay, d)` 都读它们，改一个滑块全局联动

**这两个层是给人在 AE 里调的接口**，删了整片表达式全崩。

## 层命名与分组规范

按"渲染顺序 + 内容类型"命名，让人在时间轴上能一眼找到：

```
后期：  FadeBlack / Grain / Vignette / TintSunset / TintNight / FlashVeil
文字：  LYR_00 … LYR_46（每条歌词一个预合成）
卡片：  TitleBoard / EndCard / MEMORY
粒子：  LightSpot×8 / Firefly×14 / GoldRain×18 / Petal×10 / Snow×20 / FLeaf×26
事件：  FlyPhoto×9 / Kite / MailLetter / Silhouette×2
道具：  Card×3 / Bench / Scarf×2 / Bicycle / Swing / Chime / Lamp / LampGlow /
        Mailbox / Town / Stream / DriftLeaf×6 / Fence / Log / PathStones / LeafPile
环境：  Ground×3 / SnowGround / GrassBlades / HillFar / HillNear / Cloud×3 /
        Sun / Moon / Stars / SkyTop / SkyHor
树：    HeroLeaf / Leaves0-3 / TreeTrunk
母色：  M_CANOPY×4（叶色由它驱动，四季循环靠它的 Fill Color 关键帧）
```

> 索引维度用 `×N` 后缀，不要用 `01/02/03`，AE 里层名过长会被截断。

## 兼容性坑（AE 2024 实测）

**1. 蒙版容器有两种 matchName**

```js
try { grpM = l.property("ADBE Mask Parade"); } catch(e){}   // 形状层
if (!grpM) { grpM = l.property("ADBE Masks"); }             // 素材层
```

**2. `setValueAtTime` 容易因属性类型不符抛错**
一律包 try，把失败项收集到 `KEYERR`，事后打印前 20 条。构建"成功"但几百个关键帧没打上，
是这套流程最隐蔽的故障。

**3. `property(1)/property(2)` 是位置索引，不是稳定标识**
`colorExprLayer` 里用 `Root Vectors Group > 1 > Contents > 2` 取填充色，
层里组的结构变了就会取错。要么保持"组 1 = 形状，Contents 2 = Fill"的约定，
要么改用 `masterCol()` 那种按名字取的写法。

**4. 颜色值必须是 0–1 的三元数组**，不是 0–255，不是 hex。Node 侧统一转好再注入。

**5. 字体的 `postScriptName`**
`ZCOOLXiaoWei-Regular` 这种是 PostScript 名，不是家族名。
换字体先 `app.fonts` 里查实际 postScriptName，写错会静默回退成默认字体。

**6. 表达式冷启动**
工程刚打开时，引用 `ENV`/`CAM` 的层可能错位或堆叠。这是表达式未求值，
**拖一下时间指针或按空格预览即恢复**。不要因此判断工程坏了。

## 保存与校验

```jsx
try { app.project.save(new File(OUTAEP)); say("已保存 " + OUTAEP); } catch(e) { say("保存失败:" + e); }
flushLog();
```

构建完必须核对 `_buildlog.txt`：

```
图层总数 N
KEYERR 0 条:
已保存 …
```

- `KEYERR > 0` → 有属性没打上关键帧，先查 matchName 写没写错
- 图层数明显少于预期 → 中途某个 `grp()` 抛错被吞了，加日志定位

## 分层重组（可选）

图层全在 MAIN 里会有 200+ 层，人工编辑很痛苦。
`reorganize.jsx` 做二次整理：把同类层合成预合成、按段落分组、给控制器加注释。
`gen_reorg.mjs` 负责把时间点数据注入 `reorganize.jsx` 模板。

这一步是**纯整理，不改时间轴**，所以可以反复跑。
