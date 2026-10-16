# Local Assurance — Performance Investigation (2026-10-16)

> **English summary.** This is a read-only investigation of how long hardened local assurance takes, and what
> could make it faster without weakening any check. The source tree is `main` at `e193e573`.
>
> - Host figures come from repository records and PR bodies, cited per row.
> - New measurements were taken in a 2-vCPU Linux sandbox, not on the owner's WSL host. They are not
>   certification evidence.
>
> **Main finding.** Between 7 and 15 October, four full runs were refused only after every execution gate had
> passed. Each was refused for a reason detectable in seconds to minutes: the runner's interpreter, or skip
> admission. Fail-fast checks are therefore worth more than any speed change.
>
> **Second finding.** The command used on 7–8 October
> (`--mutation-workers 4 --formal-pytest-workers 2`) ran in 2:42–2:47 on the same host. Three later runs with
> the default flags (`--mutation-workers 2 --formal-pytest-workers 1`) took 3:27–3:33.
>
> Nothing was run on the owner's machine. No assurance run or certificate was made. `main` later moved to
> `91b44e22` (PR #146); every fact and line reference below was re-checked against it (§0).

## 0. النطاق ومصدر كل رقم

- **شجرة المصدر:** `main` عند `e193e573`. ده `05522b59` (آخر SOURCE_PASS) زائد تعديل `tests/mutation_guards.py` بتاع PR #142 (14 سطر).
- **إعادة فحص على `91b44e22`:** `main` اتحرك بعد القياسات (PR #146). من ملفات الـ pipeline اتغير:
  - `core_certificate.py`: الـ registry probe، ولسه بيشغّل `sys.executable`.
  - `tests/mutation_guards.py`: قراءة آخر summary block. مالوش أثر على الوقت.
  - `tests.yml`: job الـ `reproduce` بس.
  - `recertify-hardened-core.yml`: خطوة تنظيف sparse-checkout في jobs الـ V4.
  - `LOCAL_ASSURANCE.md`: PR #145.

  `local_assurance.py` و `hardening_assurance.py` و `skip_admission.py` ما اتغيروش. أرقام السطور في الملف ده على `91b44e22`.
- **التصنيفات المستخدمة في الملف:**
  - **مقاس:** اتنفذ في الجلسة دي في الـ sandbox.
  - **مسجّل:** موجود في المستودع أو في جسم PR.
  - **تقدير:** نموذج محسوب.
- **الـ sandbox:** حاوية Linux (2 vCPU Intel Xeon @ 2.10GHz، 7 GB)، Python 3.12.3، pytest 9.1.1، pytest-xdist 3.8.0. أبطأ من جهاز WSL في وقت المحاولة الواحدة.
- **ما اتنفذش:** أي حاجة على جهاز المالك، أو local assurance كامل، أو توليد شهادة، أو commit، أو push.
- **الأوامر:** كل أمر اتنفذ ونتيجته موجودين في §14.

## 1. الخلاصة

1. **أكبر هدر هو الرفض المتأخر، مش السرعة.** من 7 لـ 15 أكتوبر، 4 تشغيلات كاملة اترفضت **بعد ما كل الـ gates عدّت**. الأسباب كانت ممكن تتكشف في 16 ثانية إلى 20 دقيقة (§4).
2. **أمر 8 أكتوبر أسرع بقياس حقيقي على نفس الجهاز.** `--workers 4 --mutation-workers 4 --formal-pytest-workers 2` أخد 2:42 و 2:46:53. تلات تشغيلات أحدث بالافتراضي (`--mutation-workers 2 --formal-pytest-workers 1`) أخدت 3:27 و 3:33 و 3:33. والأمر الرسمي في `LOCAL_ASSURANCE.md` لسه مالوش flags عمّال (§3).
3. **Formal هو المسار الحرج (~80–85%).** وقت كل طفرة تقريبًا ثابت، لأن كل محاولة بتشغّل نفس الـ 48 ملف. والجدولة الذكية مش هتفيد (§5–6).
4. **xdist (n=2) اتقاس بالأداة الحقيقية: −35% على 4 طفرات** بنفس الأحكام. على shard كامل التقدير −27% إلى −35%، بسبب تكاليف ثابتة لكل shard (§6.2).
5. **job الـ `mutations` في CI عمره ما بيخلص.** بيشغّل 284 طفرة في job واحد، والحد 6 ساعات (§7).
6. **الشهادة ما بتسجلش طريقة تشغيل Formal ولا الـ flags** (§8).

## 2. مسار التنفيذ الحالي (`tools/certification/local_assurance.py`)

`run` بيتنفذ بالتسلسل:

1. قفل، فحص نظافة الشجرة، فحص الـ HEAD، وفحص `ngspice`.
2. `fast311` ثم `fast312` (`-m "not expensive" -n 4 --dist loadfile`).
3. `scientific312` (`-m "not campaign" -n 4`).
4. `campaign312` (4 اختبارات، تسلسلي).
5. `regression312`.
6. **Formal**: 4 shards على pool حجمه `--mutation-workers`.
7. **V4**: 8 shards على pool بنفس الحجم.
8. `trust_mutations`.
9. Evidence manifest صارم.
10. `build_assurance`، ومعاه skip admission.
11. الشهادة والتحقق الذاتي منها.
12. إيصال بحالة `SOURCE_PASS`.

بعد كده الـ certificate child، و `verify` اللي بيشغّل 22 self-check.

| الاعتمادية | ضرورية؟ | السبب |
|---|---|---|
| الـ gates اللي جوه الـ checkout قبل نسخ الـ seeds | نعم | الـ seeds بتنسخ ملفات المستودع غير المتتبَّعة. لو اختبار كتب وقت النسخ، الـ seed يتلوث |
| الـ gates الرخيصة قبل الطفرات | سياسة fail-fast | مفيش اعتماد على بيانات |
| Formal قبل V4 | لأ | نسخ معزولة. التداخل محتاج تعديل في ملف مثبّت |
| manifest ← assurance ← شهادة ← verify | نعم | كل خطوة بتربط اللي قبلها |

**الـ CI بيشغّل نفس الـ 18 gate بالتوازي** (`recertify-hardened-core.yml`). كل gate مرتبطة بـ `classify` بس وليها checkout منفصل، و Formal بيتنفذ **تسلسلي** (من غير `--pytest-workers`). الـ docstring في `assert_clean_tree.py` بيشرح إن الـ checkout المنفصل هو اللي بيخلي التوازي آمن. يعني الترتيب التسلسلي المحلي سببه الـ checkout الواحد، مش شرط علمي.

## 3. سجل التشغيلات الحقيقية على جهاز WSL

| التاريخ | المصدر | الإعدادات | المدة | النتيجة | المرجع |
|---|---|---|---|---|---|
| 7–8 أكتوبر | `d5d886f9` | `--workers 4 --mutation-workers 4 --formal-pytest-workers 2` | 2:42 | **اترفض بعد كل الـ gates** في `build_assurance` (سقف الـ skips) | PROGRESS (Pass 13) |
| 8 أكتوبر | `dafa87c4` | نفس الأمر | **2:46:53** | SOURCE_PASS ← PASS | PR #119 |
| 9 أكتوبر | `3e396bc4` | مش مسجلة | مش مسجلة | SOURCE_PASS ← PASS | PR #120 |
| 9 أكتوبر | `39d43456` | مش مسجلة | **2:44** | SOURCE_PASS ← PASS | PR #123 |
| 13–14 أكتوبر | `ae25aed9` | — | 0 ث / عند FAST 3.12 | رفض مبكر (مفسّر غلط، ثم bug في xdist) | PROGRESS |
| 14 أكتوبر | `313bbf1e` | مش مسجلة | تشغيل كامل | **اترفض بعد كل الـ gates** (2 skips من غير قاعدة قبول) | PROGRESS |
| 14 أكتوبر | `05522b59` (1) | مش مسجلة | ضاع في نص Formal | restart لـ WSL | PROGRESS |
| 14 أكتوبر | `05522b59` (2) | **الافتراضي** (الأمر المسجّل من غير flags عمّال) | **3:27** (12,422 ث) | SOURCE_PASS ← PASS | PROGRESS |
| 14–15 أكتوبر | `5847345e` | **الافتراضي** (`run --reuse --repository …`) | **3:33** (22:27Z → 02:00Z) | **اترفض في assurance build**: 2 skips لاختبارات raw-data تحت `benchmarks/`، ظهروا في `fast311` و `fast312` و `scientific312` | PROGRESS (2026-10-15) |
| 15 أكتوبر | `0bc8b1cb` | **الافتراضي**، والـ runner بـ `/usr/bin/python3.12` | **3:33** (02:06Z → 05:39Z) | الـ 18 gate كلها عدّت (FAST 10,602، SCI 11,175)، و**اترفض في `certificate_generation`** (`pint` مش موجود) | PROGRESS (`a0e7db31`)، PR #145 |

**سقف المدة من وقت الـ commits** (المصدر ← الـ certificate child):

| المصدر | الفرق | ملاحظة |
|---|---|---|
| `dafa87c4` | 169 د | — |
| `39d43456` | 165 د | — |
| `3e396bc4` | 666 د | الفرق فيه شغل تاني |
| `05522b59` | 364 د | فيه المحاولة اللي ضاعت |

**ملاحظات:**
- تشغيل `0bc8b1cb` هو نفس التشغيل اللي اتطلب التحقيق ده وهو شغال؛ أرقام FAST و SCI بتطابق الطلب.
- **مقارنة على نفس الجهاز:** الافتراضي 3:27 / 3:33 / 3:33، وأمر 8 أكتوبر 2:42 / 2:46:53. الفرق 45–51 دقيقة لكل تشغيل، مع إن اختبارات 7–8 أكتوبر كانت أتقل.
- `--formal-pytest-workers 2` **اتعمل بيه فعلًا في شهادة معتمدة** (`4f610514`، PR #119). يعني قرار xdist اتاخد عمليًا في 8 أكتوبر.
- اختبارات 8–9 أكتوبر كانت **أتقل**، لأن `577451c7` (12 أكتوبر) قلّل تكلفة 3 من أتقل 4 ملفات في Formal. ومع كده الأمر ده كان أسرع بـ 40+ دقيقة.
- الأمر الرسمي في `docs/assurance/LOCAL_ASSURANCE.md` (سطر 61 على `91b44e22`، بعد دمج PR #145) **مالوش flags عمّال**. يعني بيشتغل بالافتراضي `--mutation-workers 2 --formal-pytest-workers 1`. في نفس الوقت، سطر 366 بيوصي بـ `--mutation-workers 4`.

## 4. الاكتشاف الأهم: الرفض المتأخر

| سبب الرفض | عدد المرات | اتكشف بعد | ممكن يتكشف بعد | بإيه |
|---|---|---|---|---|
| مفسّر الـ runner مش قادر يقرأ الـ production registry (`0bc8b1cb`) | 1 | 3:33 | **~16 ث** | `core_certificate.production_registry_identity(root)` في أول التشغيل (اتقاس: 15.8 ث) |
| skip بره قواعد القبول (`d5d886f9`، `313bbf1e`، `5847345e`) | 3 | 2:42 – 3:33 | **~5–20 دقيقة**؛ في `5847345e` كانت ظاهرة من أول gate (`fast311`) | `skip_admission audit` على JUnit بتاع FAST/SCI أول ما الـ gate يخلص (اتقاس: probe 1.2 ث + audit 0.3 ث) |
| restart لـ WSL | 1 | — | مش قابل للكشف | تشغيلي: منع النوم وتحديثات Windows وقت التشغيل |

**ساعات الجهاز لكل شهادة، 7–15 أكتوبر (تقدير):**
- النجاحات: 4 تشغيلات، حوالي 11.7 ساعة.
- الرفض المتأخر: 4 تشغيلات، حوالي 13.2 ساعة (2:42 + 3:33 + 3:33 مسجّلين، و `313bbf1e` تقدير).
- ضياع WSL: حوالي 1.5 ساعة (تقدير).

| المقياس | قبل | بعد الـ fail-fast | بعد fail-fast + أمر 8 أكتوبر |
|---|---|---|---|
| ساعات الجهاز لكل شهادة | **~6.6 س** | ~3.4 س | ~3.1 س |

الـ fail-fast ما بيشيلش أي فحص. الفحوص النهائية في `build_assurance` والشهادة زي ما هي، والفكرة إن نفس القواعد تتنفذ كمان بدري.

## 5. الوقت بيروح فين

### 5.1 Formal (المسار الحرج)

- **وقت الطفرة ثابت تقريبًا.** 284 توقيت من `benchmarks/core_freeze_v3/FORMAL_SHARD_*.log` (مسجّل، 16 سبتمبر):
  - الوسيط 96 ث، و p10 = 90، و p90 = 102.
  - مجموع كل shard: 6,898 / 6,787 / 6,781 / 6,942 ث.
  - الـ control: 91–109 ث.
  - يعني وقت الـ shard ≈ 72 × وقت المحاولة.
- **توزيع وقت المحاولة على الملفات** (1,140 اختبار في 48 ملف):

| الملف | sandbox (مقاس، 15 أكتوبر) | جهاز WSL (Pass 11، 7 أكتوبر، قبل `577451c7`) | طفرات الـ guard بتاعها في الملف |
|---|---|---|---|
| `tests/inference/test_grid_resolution_repair.py` | 44.6 ث (38.2%) | 49.2 ث | **7 من 284** |
| `tests/test_core_guards.py` | 35.0 ث (29.9%) | 29.7 ث | 65 |
| `tests/hybrid_uq/test_hybrid_uq_router.py` | 11.3 ث (9.7%) | 18.8 ث | 1 |
| `tests/test_core_semantic_invariants.py` | 8.9 ث (7.7%) | 21.2 ث | 7 |
| باقي الـ 44 ملف | 17.0 ث | 11.5 ث | 200 + 4 رفض استيراد |
| **المحاولة كاملة** | 128.3 ث (bare pytest) / 112–114 ث (الأداة) | 141.2 ث | — |

- **رفض الاستيراد** (`G1d` و `G14a` و `G34a` و `G34b`) موزع 3 / 0 / 0 / 1 على الـ shards. في وضع xdist، الطفرات دي بتتنفذ تسلسلي ومعاها control تسلسلي إضافي، فـ shard 0 يبقى المسار الحرج.
- **الأهداف الدنيا** (كل طفرة تشغّل الملف اللي فيه الـ guard بتاعها بس): 0.76 + 0.13 ساعة مقابل 9.21 ساعة وقت اختبار (−90%، مقاس من خريطة الـ guards). ده تغيير عقد ومراجعة علمية، مش تحسين تنفيذي.

### 5.2 باقي المراحل

| المرحلة | الرقم | النوع | الوزن التقريبي |
|---|---|---|---|
| V4، shard كامل (85 مدخل) | 273.6 ث؛ 85/85 وصلوا للحكم المعلن، والـ control أخضر (94 passed). منها 218 ث تشغيل pytest، و 45.7 ث SHA للـ seed والـ worker | مقاس | 8 shards: حوالي 6–9 د بـ 4 workers، وحوالي 12–18 د بـ 2 (تقدير) |
| Trust (20 طفرة + control) | **47.4 ث**؛ 20 killed، 0 survived، 0 invalid. كل تشغيل حوالي 2.3 ث، والـ timeout 180 ث | مقاس | <1% |
| Campaign (4 اختبارات، تسلسلي) | 261 + 103 + 33 + 32 ≈ 429 ث (`tests/conftest.py`) + تجميع الـ suite كلها (~39 ث) | مسجّل | ~3–4% |
| FAST و SCI | FAST بـ `-n 4`: 161–163 ث، وبـ `-n 8`: 101 ث؛ SCI بـ `-n 4`: 245–276 ث (`docs/TESTING.md`، Windows، 12 أكتوبر) | مسجّل | ~8–10% |
| فحص نظافة الشجرة | 5,550 ملف متتبَّع (58.5 MB)؛ `tree_problems` = 1.87 ث | مقاس | ≤1% |
| التحقق من الشهادة | ~10.4 ث (15 منطقة، 698 ملف مثبّت) | مقاس | ثواني |

### 5.3 تكاليف الـ workspace والـ bytecode

| البند | الرقم (مقاس) | الخلاصة |
|---|---|---|
| SHA snapshot لشجرة Formal (5,693 مدخل، 84.2 MB) | 0.22 ث للمرور الواحد؛ حوالي 0.9 ث لكل محاولة | ~1% من المحاولة. ما فيش داعي نلمسه |
| استيراد 718 وحدة من `engcore` من غير pyc (الوضع الحالي) | 4.05–4.26 ث | — |
| نفس الاستيراد بـ pyc عادي (timestamp) | 2.72–2.75 ث | **غير آمن**: ممكن bytecode قديم بعد طفرة بنفس الحجم والثانية |
| نفس الاستيراد بـ checked-hash في prefix خارجي | 4.89–4.93 ث | **أبطأ** من الوضع الحالي. مرفوض |
| `compileall -j 0` مع `-X pycache_prefix` | كتب 720 pyc **جوه شجرة الـ worker**، لأن عمليات forkserver ما بتورثش الـ prefix | أي تغيير في الـ bytecode محتاج هندسة ومراجعة |

## 6. التوازي

### 6.1 Mutation workers

- فيه 4 shards بس في Formal، فـ **أكتر من 4 workers مش بيفيد Formal** (بيقصّر V4 بس).
- من 2 لـ 4، Formal بيقل من موجتين لموجة.
- Pass 10 قاس 1 و 2 و 4 workers: أحكام متطابقة، و peak RSS حوالي 3.1 GB عند 4.
- الـ CI أصلًا بيشغّل كل الـ shards مع بعض.

### 6.2 xdist جوه Formal: A/B بالأداة الحقيقية (مقاس، 16 أكتوبر)

نفس 4 طفرات من shard 1 (`G1b` و `G2a` و `G6a` و `G12c`) عن طريق `tests/mutation_guards.py`:

| | تسلسلي | `--pytest-workers 2` | الفرق |
|---|---|---|---|
| الـ control | 119 ث | 65 ث | −45% |
| الطفرة (شاملة التأكيد التسلسلي) | 112–114 ث | 68–70 ث | −39% |
| الـ named-alone control | — | ~52 ث (محسوب من الـ telemetry) | جديد |
| التأكيدات التسلسلية | — | 22.2 ث لـ 4 kills | جديد |
| **الإجمالي** | **580.1 ث** | **379.3 ث** | **−35%** |
| الأحكام | 4/4 RED | 4/4 RED، ونفس أعداد الفشل (15 / 4 / 3 / 1) | متطابقة |

**التكلفة الثابتة في shard حقيقي.** الـ named-alone control بيشغّل **68 / 71 / 70 / 70** عملية pytest منفصلة (shards 0–3)، وفوقهم 71 تأكيد تسلسلي. التقدير للـ shard الكامل في الـ sandbox **−27% إلى −35%**، وده متسق مع −22% اللي اتقاس على جهاز WSL في Pass 12.

### 6.3 جدولة xdist (`--dist loadfile`)

قريت `xdist/scheduler/loadscope.py`، الإصدار 3.8.0:
- الملفات بتترتب **بعدد الاختبارات تنازليًا** (`--loadscope-reorder` افتراضي).
- كل worker بياخد ملف جديد لما يتبقى معاه ≤2 اختبار.

محاكاة بأوقات الـ sandbox الحقيقية:

| n | الـ makespan | الحد الأدنى النظري |
|---|---|---|
| 2 | 58.4 ث | 58.4 ث |
| 3 | 46.4 ث | 44.6 ث |
| 4 | 45.1 ث | 44.6 ث |

الجدولة الافتراضية قريبة من الأمثل. الحد الحقيقي هو ملف الـ grid. **n=3 ممكن يدّي حوالي −20% زيادة في وقت المحاولة، و n=4 مش بيزوّد حاجة.** محتاج تجربة على جهاز WSL.

## 7. CI

- **`tests.yml` ← job الـ `mutations`** (سطر 116–130): `python -X utf8 tests/mutation_guards.py "${RUNNER_TEMP}/mutations"` بيشغّل الـ 284 طفرة + control في job واحد.
  - ده حوالي 285 × 90–130 ث ≈ 7–10 ساعات، وحد GitHub للـ job الواحد 6 ساعات.
  - PR #143 سجّل "cancelled at 6 h 0 m" على `main`، والـ `tests-gate` فشل.
  - الـ job بيشتغل على كل PR تصنيفه `ordinary` وعلى كل push لـ `main`.
- `recertify-hardened-core.yml` بيقسم Formal على 4 jobs، فمش متأثر.

## 8. الحوكمة

- **الشهادة والـ assurance ما بيسجلوش طريقة Formal** (تسلسلي أو xdist) **ولا عدد الـ workers**. المعلومة موجودة بس في سطر `FORMAL PYTEST WORKERS N` جوه الـ transcript، ومتربوط بالـ sha بتاعه. والإيصال المحلي كمان ما فيهوش الـ flags.
- **الافتراضيات متثبّتة باختبارات:** `tests/test_local_assurance.py` (سطر 336–352) بيتأكد من `[2, 1]` و `(4, 2, 1)`.
- **تصنيف الملفات المرشحة للتعديل** (`recertification_scope explain`، مقاس):

| الملف | التصنيف |
|---|---|
| `docs/work/*.md`، `docs/assurance/LOCAL_ASSURANCE.md` | `ordinary`، من غير إعادة اعتماد |
| `tools/certification/local_assurance.py`، `tools/certification/skip_admission.py`، `.github/workflows/tests.yml` | `RECERTIFY` (certification_control) |
| `tests/mutation_guards.py` | `RECERTIFY` (harness، assurance_suites) |

## 9. قبل وبعد: كل تحسين لوحده

| # | التحسين | قبل | بعد | الدليل | المطلوب |
|---|---|---|---|---|---|
| **0** | Fail-fast: registry probe في الأول + skip audit بعد كل gate وظيفي | الرفض بعد 2.7–3.5 س | الرفض بعد 16 ث – 20 د | §3، §4 | checklist يدوي النهارده؛ والكود مع إعادة الاعتماد |
| 1 | أمر 8 أكتوبر (`--mutation-workers 4 --formal-pytest-workers 2`) | **3:27 – 3:33** (الافتراضي، 3 تشغيلات مسجلة) | **2:42 – 2:47 مسجّل**، وغالبًا أقل دلوقتي | §3؛ §6.2 | flags بس |
| 2 | n=3 بدل n=2 | — | حوالي −9 د (تقدير) | §6.3 | تجربة |
| 3 | `--workers 8` لـ FAST و SCI و regression | ~20 د | ~16–17 د | `TESTING.md` | flag + تجربة (ذاكرة) |
| 4 | pool واحد لـ Formal و V4 و trust (5–6 workers) | V4 بعد Formal | V4 جوه وقت Formal (−6 إلى −9 د) | §5.2 | `local_assurance.py` + إعادة اعتماد |
| 5 | تسجيل الـ mode والـ flags في الإيصال (والـ assurance لاحقًا) | مش مسجّل | مسجّل | §8 | `local_assurance.py` + إعادة اعتماد |
| 6 | تقسيم job الـ `mutations` في CI على 4 | بيتلغي عند 6:00 | ~2–2.6 س لكل shard (تقدير) | §7 | `tests.yml` + إعادة اعتماد |
| 7 | campaign بـ `-n 4` | ~7.5 د | ~4.5 د | §5.2 | عقد (الـ CI بيشغّله تسلسلي) |
| 8 | clone منفصل لكل gate (زي الـ CI) | تسلسل | توازي (−10 إلى −16 د) | §2 | عقد |
| 9 | 8 shards لـ Formal | 72 محاولة لكل shard | 36 | نموذج | تغيير هوية معتمدة |
| 10 | أهداف دنيا لكل طفرة | 9.21 س وقت اختبار | ~0.9 س | §5.1 | عقد + مراجعة علمية |

## 10. التصنيف

| التحسين | التصنيف |
|---|---|
| أمر 8 أكتوبر، الـ preflight اليدوي، الـ audit في نص التشغيل، منع نوم الجهاز | **SAFE WITH CURRENT CONTRACTS** |
| fail-fast في الكود، تسجيل الـ flags، pool واحد، تقسيم الـ CI، تغيير الافتراضيات | **SAFE**، بس بيلمس ملفات مثبّتة، فمحتاج إعادة اعتماد عادية |
| campaign بـ `-n`، clones منفصلة، 8 shards، أهداف دنيا، تسجيل الـ mode في schema الـ assurance | **REQUIRES CERTIFICATION CONTRACT CHANGE** |
| n=3، `--workers 8` | **NEEDS CONTROLLED EXPERIMENT** |
| pyc cache، تخفيف مرورات الـ SHA، resume أو كاش للـ gates، تحديد threads الـ BLAS | **UNSAFE / REJECT** |

## 11. السيناريوهات

| السيناريو | بيشمل | مدة التشغيل الناجح | ساعات الجهاز لكل شهادة | الجهد |
|---|---|---|---|---|
| الوضع الحالي | — | 3:27 – 3:33 | ~6.6 س (تقدير) | — |
| **محافظ (من غير كود)** | #0 يدوي + #1 + انضباط الجهاز | ~2:20 – 2:45 (تقدير؛ 2:42–2:47 مسجّل على كود أتقل) | ~3.1 س | دقايق |
| متوازن | المحافظ + #0 في الكود + #3 + #4 + #5 + #6 في إعادة اعتماد واحدة | ~2:05 – 2:30 | ~2.8 س | يوم ليومين + إعادة اعتماد |
| جريء | المتوازن + #2 + #8 + #9 | ~1:20 – 1:45 | — | أسبوع لأسبوعين + مراجعة عدائية |

## 12. تجربة مضبوطة مقترحة (على جهاز WSL، بعد الموافقة)

- **البيئة:** clone نظيف من المصدر على ext4، و `TMPDIR` على ext4. venv مثبّتة، ومفيش أي حاجة تانية شغالة، ومفيش شهادة.
- **الأداة:** `tests/mutation_guards.py [--pytest-workers N] <scratch> <ids…>`، 4 عمليات متزامنة (واحدة لكل shard)، و 8 طفرات لكل shard.
  - فيهم طفرات رفض الاستيراد الأربعة.
  - وفيهم طفرة واحدة على الأقل لكل ملف من أتقل 4 ملفات.
- **الإعدادات والترتيب:** n=1، ثم n=2، ثم n=3، بالترتيب A B C C B A، بعد تشغيل إحماء من غير تسجيل.
- **اللي يتجمع:** الوقت الكلي، و `took` لكل طفرة، و CPU و RSS، و `/proc/pressure`، والأحكام، والـ controls، ومشاكل الـ sentinel، والـ scratch المتبقي.
- **معايير القبول:** أحكام متطابقة لكل طفرة؛ صفر رفض بسبب البنية التحتية؛ ذروة RSS أقل من 60% من MemTotal؛ وتحسن ≥15% عشان يتعتمد.
- **الإسقاط:** النسب المقاسة لكل محاولة مضروبة في 72 محاولة لكل shard، زائد التكلفة الثابتة (named-alone وتأكيدات). عدم اليقين المتوقع ±10–15%.

## 13. القرار

**OPTIMIZE NOW**، في حدود اللي ما بيحتاجش كود. التشغيل الجاي (اللي هيعيد تشغيل 15 أكتوبر) يتعمل بالشكل ده:
- الـ preflight (§15 بند A3).
- أمر 8 أكتوبر بمفسّر الـ venv.
- الجهاز ما ينامش، وتحديثات Windows متوقفة.

بنود الكود (#0 في الكود، و #4، و #5، و #6) تتجمع في **إعادة اعتماد واحدة**، عشان تكلفة التشغيل الكامل تتدفع مرة واحدة.

## 14. الأوامر اللي اتنفذت ونتايجها (sandbox، 15–16 أكتوبر)

| الأمر | النتيجة |
|---|---|
| `python -X utf8 -m pytest <48 Formal TARGETS> -q -p no:randomly -p no:cacheprovider --continue-on-collection-errors --junitxml … --durations=15` في نسخة seed (`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1`) | exit 0؛ 1140 passed، 1 skipped في 127.43 ث (الوقت الكلي 128.3 ث) |
| نفس الأمر بـ `--collect-only` | 10.8 ث (15 أكتوبر)؛ 7.4 ث (16 أكتوبر، page cache دافي) |
| `python -m tools.certification.mutation_v4_runner --scratch … --ids <v4 shard 0/8> --log …` | exit 0؛ 273.6 ث؛ 85/85 entries reached their declared verdict؛ CONTROL GREEN (94 passed) |
| `python benchmarks/trust_hardening/audit/mutations.py --json … --scratch …` | exit 0؛ 47.4 ث؛ population 20، killed 20، survived 0، invalid 0 |
| `tree_problems(root)` | 0 مشاكل؛ 1.87 ث |
| `python -m tools.certification.core_certificate --verify --certificate certification/current_core_v2.json` | exit 1 في 10.4 ث. متوقع: الشهادة بتربط `05522b59` والـ HEAD هو `e193e573`. استُخدم لقياس التكلفة بس |
| `python -X utf8 tests/mutation_guards.py <scratch> G1b G2a G6a G12c` | exit 0؛ 580.1 ث؛ 4/4 killed |
| `python -X utf8 tests/mutation_guards.py --pytest-workers 2 <scratch> G1b G2a G6a G12c` | exit 0؛ 379.3 ث؛ 4/4 killed |
| `core_certificate.production_registry_identity(root)` (venv 3.12) | نجح؛ 456 evidence-code files؛ 15.8 ث |
| `/usr/bin/python3.12 -E -s -P -c "import pint"` | `ModuleNotFoundError` (نفس فئة رفض 15 أكتوبر) |
| `python -m tools.certification.skip_admission probe --out …` / `audit --suite junit_fast …` | 1.2 ث / 0.33 ث (توقيت الأداة بس، على JUnit مش من gate) |
| تجربة الـ bytecode (§5.3) | مذكورة في الجدول |
| `python -m tools.certification.recertification_scope explain <paths>` | §8 |
| محاكاة جدولة xdist، وخريطة الـ guards، وتحليل الـ transcripts | §5.1، §6.3 |

**NOT RUN:** أي حاجة على جهاز WSL بتاع المالك؛ local assurance كامل؛ توليد شهادة؛ FAST أو SCIENTIFIC كامل.

## 15. مراجعة: أسرع المشاكل اللي ممكن نخلص منها

الترتيب حسب وقت الإصلاح، وبعده الأثر. كل بند اتأكد منه في الكود، وأرقام السطور على `91b44e22`. **ولا إصلاح منهم اتنفذ.**

### المستوى A: النهارده، من غير كود ومن غير إعادة اعتماد

| # | المشكلة | الدليل | الإصلاح | وقته | بيوفّر |
|---|---|---|---|---|---|
| A1 | التشغيلات الأخيرة اشتغلت بالافتراضي، وهو أبطأ من أمر 8 أكتوبر | §3: الافتراضي 3:27–3:33 مقابل 2:42–2:47؛ `LOCAL_ASSURANCE.md:61` مالوش flags عمّال | التشغيل الجاي بالأمر اللي تحت الجدول | 0 | ~45–50 د لكل تشغيل |
| A2 | فحص PR #145 (**اتدمج على `main`** في `LOCAL_ASSURANCE.md:75`) مكتوب `(cd /tmp && .forge/venvs/3.12/bin/python …)`. المسار نسبي بعد `cd`، فالأمر **بيفشل دايمًا** بـ exit 127 حتى لو البيئة سليمة | اتجرّب في الـ sandbox (§14) | PR docs صغير: نحفظ المسار المطلق قبل `cd` (أوامر A3) | 5 د | بيخلّي الفحص يشتغل فعلًا، فبيمنع تكرار رفض 15 أكتوبر (3:33) |
| A3 | الـ registry probe بيتعمل في `certificate_generation` بس، يعني في آخر التشغيل | `core_certificate.py:1423`، وسطر `:1443` بيشغّل `sys.executable -E -s -P` | preflight قبل البداية (~16 ث) | 2 د | لحد 3.5 س لكل تشغيل محكوم عليه |
| A4 | skip admission بيتعمل في `build_assurance` بس، بعد ~3 ساعات | `hardening_assurance.py:364`، واللي بيندهها `local_assurance.py:840` | `skip_admission audit` يدوي على أدلة التشغيل نفسه أول ما `gate-scientific312.json` يظهر (~20 د). قراءة بس | 1 د | 2.5–3 س لكل تشغيل محكوم عليه (اتكرر 3 مرات في أسبوع) |
| A5 | restart لـ WSL ضيّع تشغيل في نص Formal | PROGRESS (14 أكتوبر) | خطة طاقة من غير sleep أو hibernate، وإيقاف تحديثات Windows مؤقتًا، ومفيش `wsl --shutdown` ولا تحديث Docker Desktop وقت التشغيل | 5 د | تشغيل كامل |
| A6 | `LOCAL_ASSURANCE.md` بيناقض نفسه: الأمر (سطر 61) بيشتغل بالافتراضي 2 workers، والتوصية (سطر 366) بتقول 4 | `LOCAL_ASSURANCE.md:61` و `:366`؛ ومفيش اختبار بيقرأ الملف ده | نحدّث الأمر الرسمي بالـ flags، ونضيف checklist A3/A4 (تصنيف `ordinary`)، ونسجّل n=2 كقرار مالك في `ACTIVE_PLAN.md` | 15–30 د | بيمنع إن A1 يرجع تاني |

أمر A1، من جذر المستودع:

```bash
.forge/venvs/3.12/bin/python -m tools.certification.local_assurance run \
  --workers 4 --mutation-workers 4 --formal-pytest-workers 2 \
  --python311 .forge/venvs/3.11/bin/python \
  --python312 .forge/venvs/3.12/bin/python
```

أوامر A3، قبل البداية والشجرة نظيفة:

```bash
export PYTHONDONTWRITEBYTECODE=1
PY="$PWD/.forge/venvs/3.12/bin/python"
(cd /tmp && "$PY" -E -s -P -c "import pint, numpy, scipy") && echo "deps OK"
"$PY" -c "import pathlib; from tools.certification import core_certificate as c; c.production_registry_identity(pathlib.Path('.').resolve()); print('registry OK')"
command -v ngspice
```

أوامر A4، أثناء التشغيل. ده قراءة بس، فما تشغّلش `git status` وقتها، لأنه ممكن ينشئ `index.lock`:

```bash
export PYTHONDONTWRITEBYTECODE=1
PY="$PWD/.forge/venvs/3.12/bin/python"
S=$(git rev-parse HEAD); E=.forge/assurance/$S/evidence
for g in "core-fast-311 junit-fast-3.11.xml provider-availability-3.11.json junit_fast" \
         "core-fast-312 junit-fast-3.12.xml provider-availability-3.12.json junit_fast" \
         "core-scientific junit-scientific-3.12.xml provider-availability-scientific-3.12.json junit_scientific"; do
  set -- $g
  "$PY" -m tools.certification.skip_admission audit --suite "$4" \
    --junit "$E/$1-$S/$2" --availability "$E/$1-$S/$3" || echo "STOP: $1 has an unadmitted skip"
done
```

لو ظهر `STOP`، التشغيل هيترفض في `build_assurance` على كل حال، فإيقافه ما بيضيّعش حاجة وبيوفّر حوالي 3 ساعات. الـ audit ده بيستخدم نفس الدوال اللي بيستخدمها الفحص النهائي (`admit_suite` و `policy_problems` و `protected_tests`)، فهو مجرد مجموعة جزئية منه. بيرفض بدري بس، ومش ممكن يقبل حاجة الفحص النهائي هيرفضها.

### المستوى B: ساعات، كود، وإعادة اعتماد

كل البنود دي في ملفات تصنيفها `RECERTIFY`، فالأوفر نتجمعهم في إعادة اعتماد واحدة.

| # | المشكلة | المكان | الإصلاح المقترح | الحجم | المراجعة |
|---|---|---|---|---|---|
| B1 | الـ runner ما بيعملش registry probe في الأول | `local_assurance.py:803`، جنب فحص `ngspice` | ننده `core_certificate.production_registry_identity(root)` قبل أول gate، ونرفض بنفس `CertificationError` | ~10 سطور + spec | `forge-scientific-review` (سلوك assurance) |
| B2 | الـ skip admission بتيجي متأخرة | بعد `local_assurance.py:495` و `:523` | بعد كل gate وظيفي (fast311 و fast312 و scientific312): نفس منطق `skip_admission audit` (`skip_admission.py:911–955`)، ورفض فوري. الفحص النهائي في `build_assurance` يفضل زي ما هو | ~30–50 سطر + specs | `forge-scientific-review` |
| B3 | الإيصال وسجل الفشل ما بيسجلوش الـ flags ولا مفسّر الـ runner | `local_assurance.py:884–911` والدالة `_persist` (`:342`) | حقل `invocation` فيه `workers` و `mutation_workers` و `formal_pytest_workers` و `sys.executable`. الإيصال مش جزء من الشهادة، فمفيش تغيير schema | ~10 سطور + spec | عادية |
| B4 | job الـ `mutations` في CI بيتلغي عند 6 ساعات (ما اتغيرش في #146) | `.github/workflows/tests.yml:116–130` | matrix من 4 shards بـ `mutation_population select --index i --count 4`، زي `recertify-hardened-core.yml:335–344` | ~30 سطر YAML | عادية |
| B5 | الافتراضيات 2/1 أبطأ من الممارسة المعتمدة | `local_assurance.py:64–67`؛ `tests/test_local_assurance.py:336–352` | نغيرها لـ 4/2. اختياري لو A6 اتعمل | ~5 سطور + specs | قرار مالك |

**قرار التوقيت.** إعادة الاعتماد الجاية لازمة أصلًا: الشهادة بتربط `05522b59`، و PR #142 غيّر `tests/mutation_guards.py` اللي هو مثبّت، و PR #143 بيبين إن `test_the_certificate_describes_this_tree` بيفشل على `main`.

| الخيار | المكسب | التكلفة |
|---|---|---|
| نشغّل إعادة الاعتماد دلوقتي بالمستوى A | شهادة النهارده | B1–B4 يستنوا إعادة اعتماد تانية (~2.7 س) |
| ننفذ B1–B4 الأول (حوالي يوم بالمراجعة)، وبعدين إعادة اعتماد واحدة | تشغيل كامل واحد بيغطي كل حاجة | الشهادة تتأخر حوالي يوم |

### المستوى C: مش سريع (أيام أو أكتر)

pool موحد لـ Formal و V4 و trust، وتجربة n=3، و clone منفصل لكل gate، و 8 shards، والأهداف الدنيا، وحقل Formal mode في schema الـ assurance. التفاصيل في §9–§11.

### خارج النطاق (اتلاحظ في PR #143)

- **`reproduce` (Docker):** 150 اختبار كانوا محتاجين تاريخ git، و `.dockerignore` بيشيل `.git` عن قصد. **اتعالج في PR #146:** التاريخ بيتعمله mount للقراءة بس (`tests.yml:221–232`). ما شغّلتهوش هنا.
- **Branch Policy:** HTTP 403، محتاج GitHub Pro أو مستودع عام. قرار مالك (OD-1).

## 16. المراجع

- PRs: [#119](https://github.com/sharq-labs/forge/pull/119)، [#120](https://github.com/sharq-labs/forge/pull/120)، [#123](https://github.com/sharq-labs/forge/pull/123)، [#143](https://github.com/sharq-labs/forge/pull/143)، [#145](https://github.com/sharq-labs/forge/pull/145).
- من المستودع:
  - `docs/work/PROGRESS.md` (Pass 10، و Pass 13، ومدخل 14 أكتوبر)
  - `docs/work/LOCAL_ASSURANCE_OPTIMIZATION_PASS_9.md`، `_11.md`، `_12.md`
  - `docs/assurance/LOCAL_ASSURANCE.md`، `docs/TESTING.md`، `tests/conftest.py`
  - `benchmarks/core_freeze_v3/FORMAL_SHARD_*.log`
- خارجي:
  - [pytest-xdist: distribution modes](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
  - [PEP 552: Deterministic pycs](https://peps.python.org/pep-0552/)
  - [GitHub Actions limits](https://docs.github.com/en/actions/reference/actions-limits)

---

## Integration note (2026-10-16)

This is a historical performance investigation, rechecked at `91b44e22`. The repository subsequently merged PR #148 at `36306da51`, modifying certification performance paths. The figures in this record must not be mistaken for a fresh benchmark of that later source. This documentation-only integration performs no assurance run or recertification.
