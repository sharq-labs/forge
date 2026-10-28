# إصلاحات المراجعة R1–R7 — 2026-10-28

الحالة: إصلاحات محلية محدودة على Windows؛ ليست شهادة scientific MVP.
HEAD: `dd567d53d2444950f57ffaeb9903c74d7c38f04d`، main متغير.
قبل التعديل اتراجع آخر نشاط للجلسة الأخرى «افحص المشاكل ورتبها بالأهمية»:
كانت idle وآخر turn مكتمل. التعديلات السابقة محفوظة؛ لا commit/push/merge.

## الإصلاحات وحدودها

- R1: `discovery/dataset.py` يرفض تناقض قيم أو أبعاد رمز مشترك بين features
  في نفس الصف، ويقبل وحدات متكافئة بعد التحويل. لا تغيير tolerances.
- R2/R3: مدخل جديد `engcore.mind.repsem.v2` بعقد `FamilyContract`؛ وحدات
  صريحة لكل slot/parameter/condition/constant والوقت والقياس. المحاكي يستقبل
  وحدات العقد، والنتائج والحالات ترجع لوحدات المسألة قبل residuals وsigma
  وحدود القبول. الأبعاد غير المتوافقة والوحدات affine مرفوضة.
  كود الدالة وhelpers والclosures والمتغيرات المستخدمة، بما فيها nested code،
  ومصادرها والملفات المعلنة يدخلوا الهوية. تغييرها بعد sealing يرفض.
  المدخل يستخدم Assessment والأدلة الحالية مع binding بإصدار واضح.
  **v1 تاريخي ولم يتغير؛ إصلاح R2/R3 يتطلب استخدام v2 صراحة في أي تطبيق جديد.**
  هذا ليس sandbox: Python موثوق ضمن نطاق ضيق. Modules وimports داخل الدالة
  وdynamic evaluation/I/O مرفوضة، وليست قدرات ندعي دعمها. ضمان تشغيل معادٍ
  وعزل الشبكة والعمليات خارج هذا العقد. لم يتم نقل تطبيق البطارية إلى v2.
- R4: `review_discovery_candidate` لا يرقي النتيجة اعتمادًا على role أو score
  مخزّن؛ يحتاج frozen selection وfinal data ويعيد الحساب ويطابق fingerprint.
  إزالة binding أو تبديل role لا تعيد فتح مسار legacy للترقية. هذا تحقق
  اتساق، وليس إثبات استقلال البيانات أو عزل أمينها.
- R5: بإذن المالك، v0.3 فقط يستخدم `abs(A-B)/max(abs(A),abs(B))`، وصفر
  للصفرين، مع حساب مقاوم overflow. thresholds ودقة النموذج الفردي كما هي.
- R6: نقل probe التشخيصي من جذر `.forge` إلى
  `.forge/tmp/review-probes-20261028/scientific_audit_probes_20261028.py`؛
  SHA256 قبل/بعد: `18eb54b9866ed917857258c9c61db06a8d224314d160c7033fe267d1abc0ce2d`.
  لا تجاهل جديد في ownership scanner ولا حذف محتوى.
- R7: السبب كان جمع pytest للملف الإنتاجي غير المنشور `final_test.py`
  كاختبار، فيستورد نسخة ثانية من package. اسمه الآن `final_evaluation.py`؛
  imports الحالية اتحدثت. أسماء الدوال وschema لم تتغير؛ لا تجاهل أو skip.

## دليل التنفيذ

Python المستخدم: `.venv/Scripts/python.exe`؛ `python` بدون المسار غير متاح
في هذه الجلسة. الأوامر التالية تذكر arguments بعد مسار Python.

- R1 red: 5 failed / 1 passed؛ green مع audit/ordering: 33 passed.
- R2/R3: قبل المسار الجديد، اختبار A مقابل mA وهوية محاكيين: 2 failed.
  اختبارات v2 تشمل تحويل الوحدات، رفض الأبعاد، حالة percent، constants وconditions،
  تغير artifact/code/globals، imports، replay، وبقاء عدم اليقين المجهول مجهولًا.
- R4 red: 4 failed؛ green مع audit/shared/hardening: 65 passed.
- R5 red: 2 failed / 3 passed؛ green مع zero وv3: 52 passed.
- R6 نفس اختبار `test_the_real_checkout_graph_never_contains_an_environment`:
  red 1 failed؛ green 1 passed (9.27s).
- R7 اختبار subprocess الذي يجمع discovery ثم canonical package identity:
  red 1 failed؛ green مع identity/review: 18 passed.
- تشغيل تجميعي: `-m pytest tests/mind/test_repsem_strict.py
  tests/scientific/test_discovery_shared_symbols.py
  tests/scientific/test_discovery_review_proof.py
  tests/scientific/test_discovery_audit_repairs.py
  tests/scientific/test_discovery_module_collection.py
  tests/test_trust_boundary_package_identity.py
  tests/genesis_lite/test_pair_order_v3.py
  tests/test_scientific_correctness_hardening_big1.py
  tests/test_repository_ownership.py -q --tb=short`:
  **99 passed / 1 failed / 1 existing skip، 18.18s**.
  الفشل الحقيقي المتبقي: `test_a_symlink_is_refused_never_followed`،
  WinError1314 لعدم صلاحية إنشاء symlink. لم يتم تعطيله.
- `docs/ai/check_docs.py`: PASS (metadata/local paths فقط).
- `git diff --check`: PASS؛ تحذير CRLF لملف PROGRESS ليس فشلًا.
- Regression أوسع: `-m pytest tests/mind
  tests/genesis_lite/test_genesis_lite_scoring_v3.py
  tests/genesis_lite/test_scoring_zero_v3.py tests/genesis_lite/test_pair_order_v3.py
  tests/scientific/test_discovery_review_proof.py -q --tb=short
  --junitxml=.forge/review-2026-10-28/repairs-regression.xml`:
  **944 passed، 60.58s**. يشمل replay التاريخي؛ ليس full FAST.
- المراجعة العلمية المستقلة للمصدر: PASS للإصلاحات المحدودة؛ المراجع لم
  يشغّل اختبارات. لا تشمل حماية arbitrary/malicious Python.

Full FAST بعد هذه الإصلاحات: **NOT RUN**. تقرير المراجعة السابق يحتفظ بنتيجته
123 failed / 13040 passed / 266 skipped / 22 errors ولا يصف النسخة الجديدة.
Full SCIENTIFIC، full assurance، حملة نهائية، اختبار قياسات حقيقية وتثبيت wheel:
**NOT RUN**. بوابات المشروع ما زالت مفتوحة؛ WSL/Linux مطلوب لمسار العزل
والتصديق المدعوم، لكنه لا يثبت نجاحًا علميًا. البيانات المخفية لم تُفتح.
