# Scientific MVP — checkpoint 2026-10-28

## القرار الحالي

نكمل بإصلاحات محددة، ونحتفظ بالمحرك ومكونات evidence/provenance الحالية.
Technical Stabilization وScientific MVP لسه مفتوحين. مفيش دليل جديد على تفوق
علمي، ولا نسخة بيع معتمدة. العائق الأول دلوقتي بيئة Linux قابلة للتشغيل
للبوابات وحدود العزل الحالية؛ تحويل نظام الصلاحيات والأقفال بالكامل لـWindows
مش أصغر طريق للهدف.

البداية: `main`، HEAD `dd567d53d2444950f57ffaeb9903c74d7c38f04d`، شجرة نظيفة.
النهاية: نفس HEAD مع تعديلات محلية. مفيش commit/push/merge. نتائج الاختبارات
تخص الـworking tree الموصوف لكل تشغيل، مش HEAD وحده. بصمات المصدر والأدلة
موجودة محليًا في `.forge/mvp-2026-10-28/checkpoint-manifest.json`.

## اللي اتنفذ

1. بيئة `.venv` منفصلة، Python 3.11.15 على Windows؛ تثبيت extras المعلنة
   `dev,mcp,oracles`، و`pip check` نجح. سجل الحزم في `environment.txt`.
2. إصلاح ترتيب RMSE=0: الصفر كان بيتعامل كأنه غائب ويتحوّل لـinfinity.
   التغيير دلوقتي بيفرّق بين `None` والصفر؛ مفيش تغيير tolerance.
3. `isolation_support()` بيرفض non-Linux بسبب واضح قبل استدعاء `geteuid`.
   ده إصلاح crash، مش دعم للعزل على Windows ولا إثبات security boundary.
4. بعد موافقة المالك الصريحة، إضافة `evaluator/score_v3.py` لهوية v0.3
   التطويرية: pair eligibility القديمة لازمة، ومعاها نجاح واحد من النموذجين
   بنفس معيار الدقة. bracketing فقط يرجع `indistinguishable_unresolved`؛
   الرصيد الموجب يصبح صفرًا والعقوبات السالبة تفضل كما هي. v0.2 لم يتعدل.
   الوحدة لا تقدم campaign evaluator؛ الربط بالـescrow والتحقق المستقل
   وpreregistration والإحصاء والعزل ما زالوا مطلوبين قبل أي حملة v0.3.
5. بروتوكول مقترح يفصل المعايرة/اختيار النموذج/التقييم النهائي، وصلاحيات
   المطور والمحرك والمقيّم، وميزانيات baselines وإجراءات freeze.
   الموافقة الحالية تخص FDA-05 فقط؛ باقي قرارات العلم في البروتوكول مقترحة.

مراجعة مستقلة وفق skill المستودع وجدت عيبًا في المسودة الأولى لـv0.3:
الصفر كان بيمسح عقوبات control classes. اتثبت باختبارات red ثم اتصلح.
آخر مراجعة ثابتة PASS. مراجعة وكيل AI دي مش مقيّمًا نهائيًا مستقلًا، ومش
تشغيل اختبارات من المراجع ولا تصديق علمي.

## التشغيل الفعلي

كل الأوامر أدناه استخدمت `.venv/Scripts/python.exe` من جذر المشروع، إلا
اختبار الـwheel اللي اشتغل من مجلد temp خارج المشروع وبـPython البيئة النظيفة.
السجلات محلية داخل `.forge/mvp-2026-10-28/`؛ المجلد ignored وليس حزمة تسليم
محفوظة في Git. يجب تصدير الأدلة المسموح بها عند تجهيز إصدار التسليم.

| الاختبار | النتيجة الحالية وحدودها |
|---|---|
| `-m tools.capability_maturity` | PASS قبل تعديل المصدر |
| `-m tools.certification.core_certificate --verify` | رفض الشجرة المتغيرة؛ لم نصنع شهادة جديدة |
| نفس الأمر مع `--allow-dirty` | PASS تشخيصي قبل إصلاح المصدر فقط، لا يغطي التصحيح |
| RMSE regression قبل الإصلاح | 2 failed, 4 passed |
| ordering + capability tests بعد الإصلاح | 34 passed |
| portability قبل الإصلاح | 2 failed, 2 passed |
| portability + escrow isolation tests بعد الإصلاح | 6 passed؛ لا يثبت أن namespace launcher اشتغل |
| `tools/forge_check.py --regression --workers 4` | أول تشغيل 1 failed, 278 passed بسبب نقل سطر active epic؛ استعدنا موضعه دون تغيير الاختبار. إعادة التشغيل 279 passed في 26.42 ثانية |
| `-m pytest -m "not expensive" -q -n 4 --dist loadfile --junitxml=.forge/mvp-2026-10-28/fast.xml` | **141 failed, 12939 passed, 266 skipped, 22 errors** في 691.04 ثانية؛ قبل إصلاح portability وإضافة v0.3، وبعد إصلاح RMSE. مش اختبار للشجرة النهائية ولا assurance مجمّد |
| FDA-05 assertions ضد v0.2 | 3 failed, 10 passed؛ إثبات defect صناعي محفوظ |
| FDA-05 control penalty regression ضد أول مسودة v0.3 | 5 failed, 15 passed |
| مجموعة Genesis benchmark/analysis/final-review + v3 + إصلاحي ordering/isolation | 108 passed في 15.04 ثانية قبل إضافة آخر 12 control؛ `final-targeted.log` |
| `-m pytest tests/genesis_lite/test_genesis_lite_scoring_v3.py -q` بعد آخر إضافة | 32 passed؛ تشمل كل 6 أنواع، وكلا النموذجين المحتمل نجاحهما |
| إعادة المجموعة المستهدفة بعد كل إضافات الاختبارات | **120 passed في 14.53 ثانية**؛ `complete-targeted.log` |
| SCIENTIFIC / full assurance / formal campaign / final evaluation | **NOT RUN** |

FAST failures مصنفة بالـnode IDs والـtraceback في `fast-failures.json`.
الأعداد حسب module وليست root-cause equivalence:

- mutation_workspace: 75 failures؛ local_assurance: 15؛ formal_xdist: 4 failures
  و20 teardown errors. أمثلة فعلية: symlink privilege، read-only cleanup،
  `pthread_sigmask` و`SIGKILL`، ورفض lifecycle على المنصة الحالية.
- escrow_boundary: 15؛ authority_durable_campaign: 10؛ authority_integrity: 4؛
  battery readiness: خطآن. traces فيها `geteuid` و`fcntl` وhandshake غير مكتمل.
- freeze/certificate: 8 failures؛ freeze يظهر `tree.clean`، وشهادة المصدر
  لا يجوز إعادة ربطها بالتصحيح بلا بوابات إعادة التصديق.
- mutation_startup: 3؛ escrow_isolation: 2 (تم إصلاح portability بعدها)؛
  domain_real_data: 2 بسبب بيانات provenance غير المراجعة للشجرة المتغيرة؛
  change_impact وrepository_ownership وtest_timing: فشل واحد لكل منهم.
- timing subprocess إعادة إنتاج مستقلة: exit 4 أثناء pytest collection بسبب
  Windows inaccessible temporary-directory entry، قبل تشغيل الاختبار المقصود.
  لم نضع skip أو نضعّف assertion. لا نستنتج سلامة plugin من التشغيل الفاشل.

`wsl.exe` موجود، لكن `wsl --status` و`wsl --list --quiet` رجعوا exit 1:
"The system cannot find the file specified". Docker وngspice غير ظاهرين في PATH.
لم نثبّت OS/runtime أو نغيّر صلاحيات النظام. لا نفترض إن تاريخ WSL القديم
في PROGRESS يصف البيئة المتاحة حاليًا.

## التغليف وإعادة الإنتاج

تم بناء wheel محليًا بعد إصلاح RMSE وقبل إصلاح isolation:
`pip wheel . --no-deps --wheel-dir .forge/mvp-2026-10-28/wheels`.
SHA-256: `59de528e47598c03988216ab07ce7eaabd6eef3b6fc449ec54e526f4e38ca515`.
تم تثبيته في buyer-env نظيفة واختبار import من site-packages خارج المستودع
باستخدام `-I` وتحويل 1000 mA إلى 1 A. ده **smoke فقط** للنسخة المذكورة،
مش إعادة إنتاج للنتائج العلمية ولا wheel للشجرة النهائية. نسخة v0.3 الحالية
داخل benchmarks وليست واجهة مكتبة منشورة في هذا الـwheel.

## البيانات الحقيقية

فحص metadata فقط، بدون تنزيل أو قراءة بيانات تقييم نهائي جديدة:

- [Zenodo Chen2020 record](https://zenodo.org/records/4032561):
  [API metadata](https://zenodo.org/api/records/4032561) بتاريخ المراجعة
  يرجع `access_right=open` و`license.id=cc-by-4.0`.
  ده مرشح لقياسات بطارية؛ metadata الترخيص وحدها لا تثبت المعايرة أو كفاية
  uncertainty أو استقلال split. يلزم مراجعة attribution والملفات الداخلة
  بالضبط وحق إعادة توزيع حزمة البيع قبل التسليم.
- [NASA battery aging catalog](https://data.nasa.gov/dataset/li-ion-battery-aging-datasets):
  License not specified؛ لا نعتبره إذن إعادة توزيع. وصف sampling لا يعوّض
  شهادات معايرة الحساسات أو uncertainty لكل قناة.
- Thevenin/Rint مسار ملائم لتقدير معاملات ومقارنة/رفض نموذج محدود؛ وجوده
  لا يثبت اكتشاف بنية المعادلة. datasets المستخدمة تاريخيًا ليست final جديدة.

## تقدير التكلفة قبل الموافقة

**MEASURED** على Windows، أربعة workers: FAST = 11.52 دقيقة wall؛ regression
= 26.42 ثانية. حاصل wall × workers مش CPU مقاس، ومش توقع أداء Linux.
الحزم/الـwheel/local tests لم تستخدم خدمات مدفوعة.

**UNMEASURED**: تكلفة SCIENTIFIC/full assurance على بيئة مدعومة، ووقت أقوى
baseline تحت العزل، والذاكرة/CPU للحملة المصححة. قياس v0 تاريخيًا (85.07 ثانية
في PERFORMANCE.md) مش توقع صالح للـv0.3 المعزول.

المقترح القابل للموافقة لاحقًا، بعد تجهيز Linux وscorer/baselines:
pilot صناعي للتكلفة فقط، سقف wall 30 دقيقة، حتى 4 workers، بدون خدمات مدفوعة،
ولا hidden final data. نسجل CPU/wall/peak memory/observations/startup/replay
والـtimeouts، ثم نقدّر تكلفة المصفوفة الفعلية وتفاوت الزمن. سقف 30 دقيقة
**PROPOSED CAP**، مش تكلفة مقاسة ولا موافقة حالية. full assurance له تقدير
وسقف منفصلان؛ لا يوجد رقم إجمالي موثوق قبل قياس البيئة/الحالات.

تقدير جهد بشري أولي بعد توفير البيئة: 1–3 أيام لتصنيف وإغلاق أعطال التشغيل
المتبقية، 3–6 أيام لحدود البيانات والوحدات وربط الهوية، 4–8 أيام لربط scorer
والعزل والـbaselines والإحصاء، 2–5 أيام لمراجعة التطبيق الحقيقي، ثم 2–4 أيام
للتجميد والتشغيل المستقل والتسليم بعد الموافقات. **ESTIMATED** لمهندس واحد
ومراجع علمي جزئي؛ 3–6 أسابيع تقويمية تقريبًا، لا تشمل انتظار البيانات أو
المقيّم أو إعادة تصديق مطولة. أي تغيير في النموذج/حقوق البيانات/استقلال
التقييم يستدعي إعادة التقدير. مفيش وعد بتفوق علمي في المدة دي.

## اللي لسه مفتوح

لا نغلق WP-02 أو WP-04..13: calibration/selection/final وفصل lineage، وحدة
القياس وهوية التنفيذ، counter-scorer/replay، إحصاء null مضبوط، baseline
eligibility بكل أنواع الحالات، عزل launcher الفعلي، بيانات حقيقية صالحة،
بوابات نظيفة وإعادة تصديق، ثم تشغيل مستقل وتغليف نهائي.

المالك هيعيّن المقيّم لاحقًا. لم يعتمد باقي البروتوكول أو ميزانيات الحملات.
الخطوة التالية: توفير/إصلاح بيئة Linux مدعومة وإعادة قياس البوابات عليها؛
لا نخفي الفشل الحالي بتوسيع tolerances أو حذف الاختبارات أو تعديل الأدلة القديمة.
