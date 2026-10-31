# مراجعة واسعة للريبو — 2026-10-28

## القرار

**CHANGES REQUIRED.** نحتفظ بالبنية الحالية ونكمل إصلاحات محددة؛ مفيش دليل
يستدعي إعادة كتابة المشروع. لكن عبارة «كل المتبقي محتاج WSL» مش دقيقة على
مستوى المشروع كله: فيه مشاكل علمية وهوية وتشغيل محلي ما زالت مفتوحة.
WSL مطلوب لمسار التصديق والعزل الحالي، لكنه مش هيصلّح المشاكل العلمية دي.

المراجعة دي لم تعدّل implementation أو اختبارات أو ملفات الجلسة التانية.
المخرجات تقرير وأدلة محلية فقط. لا commit/push/merge، ولا حملات أو full assurance.

## النسخة وحدود التغطية

- HEAD: `dd567d53d2444950f57ffaeb9903c74d7c38f04d`، فرع `main`، working tree
  متغير، وفيه شغل جلسة تانية معروف للمالك. النتائج ليست شهادة للـHEAD وحده.
- سجلنا SHA-256 لـ2,539 ملف source/config tracked أو nonignored قبل FAST
  وبعده؛ لا اختلاف في المجموعة أو البصمات. ده لا يشمل scratch ignored أو
  حالة النظام، ولا يحوّل التشغيل لـimmutable assurance.
- فحص AST لـ1,615 ملف Python في src/tools/providers/flagships/tests: بلا
  أخطاء syntax. قراءة علمية موجهة لمسارات الاكتشاف والتقييم وrepsem وبعض
  providers، مع مراجعة مستقلة للتغييرات العلمية واختبار FAST على الريبو.
- ده أوسع من targeted tests، لكنه مش قراءة سطر بسطر لكل ملف، ولا إثبات
  خلو المشروع من الأخطاء. لم نقرأ بيانات تقييم نهائي مخفية أو seeds جديدة.

## التشغيل الحالي — مش نتائج تاريخية

بيئة Windows، Python 3.11.15 من `.venv/Scripts/python.exe`، نفس البيئة
الموجودة. التفاصيل في `.forge/review-2026-10-28/` (ignored؛ تحتاج حفظًا ضمن
حزمة الأدلة لاحقًا). `environment.txt` يسجل الحزم الفعلية.

| الأمر/الفحص | النتيجة |
|---|---|
| `python -m pytest -m "not expensive" -q -n 4 --dist loadfile --junitxml=.forge/review-2026-10-28/fast.xml` | **123 failed, 13040 passed, 266 skipped, 22 errors**، 648.22 ثانية، exit 1 |
| `python -m pip check` | PASS، لا broken requirements؛ ليس clean-install proof |
| `python docs/ai/check_docs.py` | PASS، 9 metadata documents فقط، ليس فحص كل صحة التوثيق |
| `python -m tools.capability_maturity` | دفتر القدرات متسق؛ لا ترقية علمية |
| `git diff --check` | PASS؛ تحذير نهايات أسطر PROGRESS فقط |
| `python -m tools.certification.core_certificate --verify --allow-dirty` | FAIL: اختلاف core/certification_control/verdict_authority عن الشهادة |
| فحص AST | 1615 ملفًا، صفر syntax errors |
| الاختباران الجديدان في FAST، منفردين | 1 failed، 1 passed، 10.03 ثانية |
| `python -m pytest tests/test_trust_boundary_package_identity.py -q --tb=short` | 9 passed في 3.09 ثانية؛ لا يمحو فشل الاختبار في FAST |
| SCIENTIFIC / Linux isolation / full assurance / final campaign | **NOT RUN** |
| بناء وتثبيت wheel من هذه النسخة الحالية | **NOT RUN**؛ smoke القديم ليس دليلًا للنسخة الحالية |

المقارنة مع FAST السابق: 20 failure/error IDs لم تعد تظهر، وظهر فشلان جديدان.
ده فرق أسماء نتائج، مش برهان إن الأسباب كلها اتصلحت أو إن الفشلين جديدان
في production. `comparison.json` يحفظ القائمتين. في المجمل عدد failures
انخفض من 141 إلى 123، مع بقاء 22 errors.

## المشاكل ذات الأولوية

### R1 — P1: رمز واحد له قيم متناقضة في نفس العينة

المصدر: `src/engcore/scientific/discovery/dataset.py:39` و`:83`.
كل feature بيتحقق من bindings الخاصة به، لكن dataset لا يوحّد معنى الرمز
المشترك بين features. مثال صناعي منفّذ: عمود باسم linear يعلن `Symbol(x)`
بقِيَم 1..6؛ عمود باسم square يعلن نفس `Symbol(x)` بقيم 1,4,9..36. كل واحد
له bindings توافق عموده. المحرك يقبل الاثنين ويختار square بمعامل 1 وخطأ
اختيار صفر؛ الوصف الرمزي لا يمثل حالة متغير واحدة متسقة.

الأثر: نتيجة تبدو كعلاقة مكتشفة دقيقة رغم تناقض تمثيل المدخلات.
أصغر إصلاح: توحيد bindings الرموز المشتركة على مستوى كل صف أو رفض التعارض
باستخدام مقارنة وحدات صحيحة. لا حاجة لطبقة Evidence جديدة.
القبول: التعارض يرفض، bindings المتفقة والوحدات المكافئة تمر، ونفس الشرط
يسري على بيانات final. دليل التنفيذ: `shared-symbol-control.json`.

### R2 — P1: مسار repsem لا يفرض وحدات العائلة أو يحوّلها عند الربط

المصدر: `src/engcore/mind/repsem/families.py:33` و`:110–130`.
`FamilySlot` يحدد الدور فقط، و`bind_trajectory` يحوّل الأرقام مباشرة إلى
NumPy arrays. مثال منفّذ: 1 A يصل كـ1، و1000 mA يصل كـ1000، وقناة معلنة kg
تُقبل في نفس slot. دالة العائلة لا تستلم جدول الوحدات لتعرف الفرق.

الأثر: الوحدات المتكافئة قد تغيّر المدخل الرقمي بمعامل 1000؛ الدور وحده
لا يثبت صلاحية البعد الفيزيائي. ده finding عن واجهة الربط، مش ادعاء إن كل
تشغيل بطارية تاريخي أخطأ؛ قد تكون بياناته مطبّعة مسبقًا.
أصغر إصلاح: عقد وحدات/أبعاد للعائلة وتحويل عند الحد باستخدام Quantity الحالي،
ورفض dimension mismatch قبل simulate. القبول: A/mA وs/ms متكافئين ينتجوا
نفس المدخل المطبّع، وkg بدل A يرفض. دليل: `repsem-controls.json`.

### R3 — P1: هوية العائلة في repsem لا تربط دالة التنفيذ

المصدر: `src/engcore/mind/repsem/families.py:56–67`، واستخدام family.to_dict
داخل `src/engcore/mind/repsem/assess.py:524`.
مثال منفّذ: عائلتان لهما نفس metadata لكن simulate مختلفان، وto_dict متطابق.
تساوي نواتج مجموعة عينات بعينها في replay لا يثبت تطابق التنفيذ خارجها.

الأثر: تعريف النموذج المسجّل لا يكفي لتحديد التنفيذ الذي أنتج الدليل.
أصغر إصلاح: bind لهوية implementation/version/config/dependencies في عقد
العائلة والسجلات الحالية، مع versioning يحفظ الأدلة القديمة؛ لا تعتمد على
اسم الدالة وحده. القبول: تغيير التنفيذ مع نفس family_id يغيّر هوية الدليل
ويرفض خلط replay القديم بالجديد، حتى لو تطابقت نواتج عينات معينة.
الدليل: `repsem-controls.json`. لم ننفذ حملة replay جديدة.

### R4 — P2: تغيير evaluation_role وحده يرقّي قرار المراجعة

المصدر: `src/engcore/scientific/discovery/candidate.py:68–73` و
`src/engcore/scientific/discovery/campaign.py:62–73`.
مثال منفّذ: `replace(candidate, evaluation_role="final_test")`، مع نفس
selection binding والخطأ، يغيّر review من CANDIDATE إلى HOLDOUT_SURVIVOR
بدون استدعاء evaluator. ده اعتماد على caller metadata، **مش** إثبات اختراق
خزنة أو قراءة الحقيقة أو الحصول على independent verification.

أصغر إصلاح: ترقية final فقط بعد التحقق من result/binding المطابقين للـfrozen
selection وfinal data؛ الدور وحده يظل غير مثبت. حافظ على قراءة التاريخ
بدون جعله دليل final جديد. القبول: relabel وحده لا يرقّي، evaluation الصحيح
يمر، والنتيجة أو الربط المعدّلان يرفضان. دليل: `relabel-control.json`.

### R5 — P2: ترتيب الزوج يغيّر نتيجته ودرجته

المصدر: `benchmarks/genesis_lite/evaluator/score_v3.py:46–50`.
الفرق النسبي يستخدم القانون الثاني فقط في المقام. مثال منفّذ: inbox truth=1،
تنبؤا القانونين .99 و1.01، tolerance=sigma=.02؛ خارج الصندوق التنبؤان 1 و100
والحقيقة 1. ترتيب A,B يعطي hit/+1؛ B,A يعطي miss/−1.

العيب موروث من v2، لكنه باقٍ في v3. أصغر إصلاح يحتاج قرارًا علميًا صريحًا
عن مسافة متماثلة ومعنى الصفر في الإصدار الجديد، بدون تغيير v2 المجمد.
القبول: swap invariance للدرجة والنتيجة على حدود tolerances والصفر والقيم
السالبة. دليل: `pair-order-control.json`.

### R6 — P2: ملف تشخيص ignored داخل نطاق تعتبره أداة الملكية source

الاختبار `tests/test_repository_ownership.py:131` فشل في FAST ومنفردًا لأن
الخريطة تضم `.forge/scientific_audit_probes_20261028.py`.
`tools/test_impact.py:263` يستخدم owned_files، وحدود الاستبعاد في
`tools/certification/ownership.py:48` هي `.forge/venvs`, `.forge/tmp`,
`.forge/cache`، مش `.forge` كله. لا نسمّي ده عطل Windows أو نوسّع التجاهل
بحيث نخفي source حقيقيًا tracked.

أصغر إصلاح: صاحب السكربت ينقل التشخيص لموقع scratch معتمد أو خارج الريبو
مع حفظ الدليل؛ أو يراجع عقد الملكية إن كان المقصود غير ذلك. القبول: diagnostic
scratch لا يدخل graph، وtracked source داخل أي مكان يظل محسوبًا.
لم ننقل أو نحذف ملف الجلسة التانية. `new-failures-targeted.log` يحفظ الإثبات.

### R7 — P2 / السبب غير محسوم: هوية الحزمة تفشل ضمن المجموعة فقط

`tests/test_trust_boundary_package_identity.py:136` فشل داخل FAST:
`import_module('src.engcore') is engcore` رجعت false. الاختبار منفردًا نجح،
وكل ملف اختبارات الهوية نجح (9). ده دليل فشل تكاملي محتمل مرتبط بترتيب
imports/حالة العملية؛ السبب **UNKNOWN**، مش root cause مثبت.

الأثر المحتمل: نسختان من class identities تكسر isinstance وربط العقود.
الخطوة المناسبة: عزل ترتيب الاختبارات/imports في نفس worker وإنتاج minimal
reproducer قبل تعديل alias أو tests. القبول: reproducer ثم تشغيل المجموعة
التي كانت تفشل، مع الحفاظ على هوية canonical وقراءة المسارات التاريخية.
لا نعتبر النجاح المنفرد إغلاقًا للفشل الجماعي.

## بوابات تمنع التسليم ولا تُختزل في findings السابقة

- باقي FAST يتضمن mutation_workspace (75 failures)، escrow_boundary (15)،
  authority_durable_campaign (10)، formal_xdist (4 failures و20 teardown
  errors)، authority_integrity (4)، وثمانية certificate/freeze failures،
  واثنين provenance، وحالات أخرى محددة في `fast-failures.json`. أسباب Windows
  السابقة شوهدت في traces، لكن نجاحها على Linux لم يُختبر هنا.
- اختلاف الشهادة الحالي مقصود كشفه، مش عطل يتصلح بتحديث البصمات بلا بوابات.
  بيان التغييرات في `certificate.log`. يلزم مصدر مجمد ومراجعة وتصديق جديد
  بحسب العقد والموافقة المنفصلة للميزانية.
- SUNDIALS provider الموجود contract-only ويعلن unavailable؛ وجود الاسم
  لا يدعم claim إنه يحل DAE. دفتر القدرات يضع battery.thevenin_1rc في FUNCTIONAL
  مع independent_validation غير مكتمل. لا نرقّيه بسبب وجود بيانات حقيقية فقط.
- v3 scorer/statistics ما زالوا DEVELOPMENT_ONLY وlift_claimed=false. ده
  fail-closed مفيد، لكنه لا يعوّض حملة blindfold مستقلة أو baselines مؤهلة.
- clean install للنسخة الحالية، SCIENTIFIC، الحدود الأمنية الفعلية، حقوق
  بيانات التسليم النهائية، وتشغيل المشتري المستقل ما زالت بوابات منفصلة.

## أفضل خطوة تالية

ابدأ بإغلاق R1 مع صاحب جلسة الاكتشاف؛ عيب تمثيل مثبت، مستقل عن Windows،
وله إصلاح صغير واختبار قبول واضح. بالتوازي يمكن تجهيز Linux للبوابات، لكن
لا تُعلن Technical Stabilization أو Scientific MVP مكتملًا قبل إزالة
الأعطال الإلزامية وتقييم علمي صالح. المراجعة المستقلة للتغييرات: CHANGES REQUIRED؛
المراجع لم يشغّل الاختبارات، والأمثلة أعلاه شغّلها المراجع الرئيسي هنا.
