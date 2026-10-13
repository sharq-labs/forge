# 08 — Trust-to-Evidence & External Pilot Readiness

**تاريخ الإضافة:** 2026-10-14. **نوع العمل:** كتالوج بحثي مكمل، لا خطة تنفيذ، ولا شهادة، ولا تقرير عيوب مؤكدة على HEAD الحالي.

**نقطة القراءة:** `main@79d2b474d2cc77cad32f2b3278f4535b5d90ae95`. تمت قراءة ملفات `gaps/01–07` والفهرس والمصادر و`CLAUDE.md` و`ACTIVE_PLAN.md` وسياسة نضج القدرات وعينة من مسارات `claims` و`product` و`engineering/bundle`. **اختبارات أو أمثلة مضادة في هذه المهمة: NOT RUN**. ملاحظات تدقيق 2026-10-13 تخص SHA أقدم؛ لا تُحوَّل تلقائيًا إلى أخطاء مؤكدة في SHA جديد.

هذه الإضافة تركز على الانتقال من **ميزة علمية داخل المستودع** إلى **حكم قابل للتدقيق من طرف خارجي** ثم تجربة مجانية محدودة يمكن أن تخلق دليل استخدام حقيقيًا. لا تمنح Pilot ناجحًا مرتبة `EVIDENCE_BACKED` أو `PRODUCTION_READY` إلا عبر سياسة النضج الرسمية.

## خريطة الفجوات الجديدة

| المعرف | الفجوة البحثية المحددة | أول دليل نجاح مطلوب | السهولة | التأثير | يرتبط بـ |
|---|---|---|---|---|---|
| T01 | [ملكية معايير المقارنة وSource Grounding](#t01) | لا يمكن تغيير شرط مقارنة دون مصدر موثق | ★★★☆☆ | ★★★★★ | G04، N05 |
| T02 | [الحد الأدنى للأدلة من Risk Policy](#t02) | LLM لا يخفض evidence/UQ bar | ★★★☆☆ | ★★★★★ | G05، N01 |
| T03 | [منع خلط أدوار المدخلات والوحدات](#t03) | نفس العدد بوحدة أو خاصية أخرى لا يمر كدليل | ★★★☆☆ | ★★★★★ | C01، G02 |
| T04 | [مصدر صلاحية النموذج والمعاملات](#t04) | توسيع envelope بلا مصدر لا يزيد الدعم | ★★☆☆☆ | ★★★★★ | C02، X01، X08 |
| T05 | [صدق تسميات Verification/Validation في كل المخرجات](#t05) | benchmark عددي لا يصير دليلًا تجريبيًا | ★★★☆☆ | ★★★★★ | C09، R14، N01 |
| T06 | [سلسلة ضمانات مرتبطة بالـSHA ومسار الحكم](#t06) | تغيير authority يفرض بوابة تحقق ملائمة | ★★☆☆☆ | ★★★★★ | R06، N02، N04 |
| T07 | [حملة False-SUPPORTED هجومية](#t07) | الحالات المخالفة ترفض دون ترقيات صامتة | ★★★☆☆ | ★★★★★ | C04، G03 |
| T08 | [بروتوكول بيانات تجريبية مستقلة ومخفية](#t08) | Hold-out جديد محجوب وفحص leakage موثق | ★★☆☆☆ | ★★★★★ | P12، R14، X01 |
| T09 | [حزمة قبول لمختبر خارجي على جهاز نظيف](#t09) | مستخدم مستقل يعيد تجربة وحدودها ويرسل Feedback | ★★★☆☆ | ★★★★★ | N04، N10، P11 |
| T10 | [حقوق إعادة الاستخدام وأدلة المشتري](#t10) | أصول وبيانات واعتماديات قابلة للتدقيق القانوني | ★★★★☆ | ★★★★☆ | G03، N09 |

**معنى النجوم:** نفس معنى الفهرس الرئيسي؛ تقييم تحليلي لحزمة محدودة، لا نتيجة Benchmark ولا ضمان نجاح. البنود المقصودة هنا **زوايا قبول جديدة** فوق قدرات قائمة، وليست إنشاء Evidence Graph أو Verdict Engine أو UQ مستقل.

<a id="t01"></a>
## T01 — ملكية معايير المقارنة وSource Grounding

- **الحاجة:** المدخلات الفيزيائية ليست وحدها ما يغير النتيجة؛ `target` و`operator` و`tolerance` و`QoI` يحددون معنى السؤال نفسه. يجب أن يكون مصدرها مميزًا عن اقتراح الـAI.
- **الموجود/مسار الجرد:** `src/engcore/claims/adapters/nl.py` و`src/engcore/product/runtime.py` و`src/engcore/claims/verdict.py`. لا يُفترض أن مسار الإدخال الحر هو نفسه مسار Structured API.
- **أصغر تجربة:** سؤال له حد صريح؛ بدّل حد المقارنة أو اتجاهها في proposal مع إبقاء المدخلات نفسها. تحقق من `prepare` و`run` ونسخة السجل الموقعة/القابلة لإعادة القراءة.
- **القبول:** المقارنة غير المسندة تظل `NEEDS_INPUT` أو `REFUSED` / غير قابلة للحكم، ولا تصبح `SUPPORTED`. مصدر الشرط يُحفظ للمدقق؛ لا تكفي مطابقة رقم في أي موضع.
- **المالك:** Claims/Product boundary، لا MCP ولا Scientific Core للقراءة اللغوية. **التميّز عن G04:** G04 يتتبع مدخلات التنفيذ؛ هذا البند يثبت هوية *السؤال المقيَّم*.

<a id="t02"></a>
## T02 — الحد الأدنى للأدلة من Risk Policy

- **الحاجة:** لا يصح أن يختار المقترِح درجة الأدلة أو قنوات عدم اليقين التي تكفي لقرار علمي عالي الأثر؛ سياسة المخاطر لا تأتي من نص يصوغه النموذج.
- **مسار الجرد:** `src/engcore/claims/verdict.py`، إعداد `decision_context`، ومصدر تطبيق السياسة في مسار المنتج. راجع العلاقة بين `UNKNOWN` و`None` وقواعد القبول.
- **أصغر تجربة:** نفس claim يرد إلى طريقين؛ واحد بمتطلبات مستخرجة من proposal، والثاني بمتطلبات policy موثقة. جرّب إزالة قنوات UQ وخفض مستوى الأدلة.
- **القبول:** لا يستطيع proposal تخفيف floor معتمد، وغياب سياق السياسة يُعلن صراحة دون أن يتحول تلقائيًا إلى موافقة. عدم كفاية الأدلة لا يُسمى تناقضًا.
- **المالك:** Policy/Claims admission. **الفرق عن G05:** G05 يفصل أنواع UQ؛ هنا نتحقق *من له سلطة تحديد الحد المطلوب*.

<a id="t03"></a>
## T03 — منع خلط أدوار المدخلات والوحدات

- **الحاجة:** وجود العدد الصحيح في النص لا يعني صحة ارتباطه بـfield؛ ويجب تفريق التمثيل الحر للوحدات عن التكافؤ الفيزيائي المصرّح به.
- **مسار الجرد:** `src/engcore/claims/adapters/nl.py` وContracts للوحدات في Scientific Core.
- **أصغر تجربة:** بدّل مكان قيمة بين `conductance` و`heat_capacity` مع تساوي المقدار، ثم جرّب 300 K مقابل 300 °C، والنفي، والشرط، وتصحيحًا في جملة لاحقة.
- **القبول:** الهوية والوحدة والمعنى والسياق متوافقة، أو تُرفض/تطلب مراجعة. التحويل الصحيح لا يغير الفيزياء؛ تطابق الأرقام وحده غير كاف.
- **المالك:** NL adapter فوق سجل الوحدات الرسمي. **الفرق عن G02:** G02 يضبط data contract بعد فهم المعنى؛ هذا يختبر الالتقاط الآمن لمعنى النص.

<a id="t04"></a>
## T04 — مصدر صلاحية النموذج والمعاملات

- **الحاجة:** caller-declared bounds قد تختلط بمنطقة صلاحية ثبتت بالقياس أو datasheet. صحة المقارنة مع limit لا تثبت مصدر limit نفسه.
- **مسار الجرد:** `src/engcore/claims/capabilities.py` و`src/engcore/product/capabilities.py` ومدخلات battery/electrothermal، مع عقود calibration والمواد القائمة.
- **أصغر تجربة:** Claim عند نقطة خارج المجال الموثق؛ غيّر رقم الحد في request فقط من غير تغيير parameter-set أو وثائق المصدر.
- **القبول:** لا ترتفع صلاحية النتيجة لمجرد توسيع حد كتبه caller؛ provenance للنطاق، إصدار parameter set، ونطاق المعايرة جزء من قرار applicability. غير المعروف يظل UNKNOWN.
- **المالك:** Domain applicability + parameter provenance، مع استهلاك claims للحكم فقط. **الفرق عن X01:** X01 قابلية تحديد المعاملات؛ هنا سلطة ونطاق سريان المعاملات نفسها.

<a id="t05"></a>
## T05 — صدق تسميات Verification/Validation في كل المخرجات

- **الحاجة:** اتفاق benchmark مرجعي أو solverين لا يثبت مطابقة تجربة حقيقية؛ تكرار وصف خاطئ عبر واجهة المستخدم والتقارير يجعل الخطأ مؤثرًا تجاريًا.
- **مسار الجرد:** `src/engcore/scientific/results/validation.py` و`src/engcore/scientific/oracles.py` و`src/engcore/credibility/` و`src/engcore/claims/`.
- **أصغر تجربة:** reference-only benchmark، وcross-solver case، وقياسات حقيقية ذات صلاحية؛ قارن basis في السجل والـAPI والتقرير وعرض maturity.
- **القبول:** لا يحصل reference-only/cross-solver على `EXPERIMENTALLY_VALIDATED` أو معنى تجريبي مكافئ؛ خطأ التسمية لا يختفي أثناء serialization أو العرض.
- **المالك:** Semantic classification في Scientific Core، ثم adapters تعرضها دون ترقية. **الفرق عن R14:** لا نضيف تجربة؛ نمنع إساءة تسمية ما لم يُجرَّب.

<a id="t06"></a>
## T06 — سلسلة ضمانات مرتبطة بالـSHA ومسار الحكم

- **الحاجة:** شهادة للكور وحده لا تكفي لإثبات سلامة طبقة تصدر `SUPPORTED`؛ كذلك لا تفيد شهادة قديمة لسلسلة تغييرات جديدة.
- **مسار الجرد:** `tools/certification/core_certificate.py`، نطاق dependency/closure، `authority/` و`claims/`، و`.github/workflows/` وسياسة حماية الفرع.
- **أصغر تجربة:** غيّر مسارًا يؤثر على معيار الحكم أو مصدر الدليل داخل checkout مؤقت، ثم تحقق أن التصنيف والاختبار الإجباري والشهادة تعلن drift أو ترفض.
- **القبول:** شهادة وسلسلة Gates مقيّدة بالـSHA الفعلي والمسار الحساس؛ لا ادعاء بأن workflow موجود يعني أن GitHub يفرضه. لا تعديل شهادة لتجاوز إخفاق.
- **المالك:** Certification/CI control plane مع owner-run recertification. **الفرق عن R06:** اختبار قابل لإعادة التنفيذ شيء؛ إثبات أن تغيير *سلطة الحكم* خاضع له شيء آخر.

<a id="t07"></a>
## T07 — حملة False-SUPPORTED هجومية

- **الحاجة:** آلاف اختبارات happy path لا تحدد احتمال إصدار `SUPPORTED` عندما تتلف الهوية أو الدليل أو ترتيب النوافذ أو شروط القرار.
- **مسار الجرد:** `tests/claims/` و`tests/test_authority_integrity.py` والاختبارات العدائية و`src/engcore/execution/multiphysics/runtime.py`.
- **أصغر تجربة:** جدول حالات هجومية: threshold/operator، وحدة وfield، evidence floor، benchmark-to-validation، stale evidence، failed early conservation window، forgery/authority genesis. لكل حالة أصل صحيح ونسخة متلاعب بها.
- **القبول:** لا يمر mutant يمس قاعدة حماية أساسية دون test kill مناسب؛ لا تؤدي إزالة الأدلة أو إخفاء فشل نافذة إلى ترقية علمية. نتائج الحملة تحفظ أسماء اختبارات وفشلها في SHA محدد، ولا تخلط القتل بممارسة Validation.
- **المالك:** Tests/assurance فوق العقود القائمة. **الفرق عن C04:** C04 حالات ربط مرجعية؛ هذا اختبار *سلطة إصدار الحكم* تحت التلاعب.

<a id="t08"></a>
## T08 — بروتوكول بيانات تجريبية مستقلة ومخفية

- **الحاجة:** calibration والـhold-out غير المستقل أو الذي اطلع عليه المطور لا يصنع إثباتًا خارج العينة، حتى لو أعاد تشغيل نفس النتائج بنجاح.
- **مسار الجرد:** `src/engcore/claims/measurement_dataset.py`، `docs/discovery/FORGE_GENESIS.md` وسياسة Capability Maturity، وتجارب battery في `benchmarks/`.
- **أصغر تجربة:** Capability موجودة واحدة (battery أو electrothermal)، preregistration قبل إتاحة hold-out جديد، تعريف device/cell/series/time split مستقل، معيار خطأ مسبق، وعمليات leakage audit بواسطة مُقيِّم خارجي.
- **القبول:** يُبلّغ PASS أو FAIL مع confidence/uncertainty والـapplicability؛ لا تعديل threshold بعد كشف النتائج، ولا ترقية تلقائية للـledger. فتح مجموعة عمياء يبطل صلاحيتها كاختبار مستقبلي مخفي.
- **المالك:** Domain validation + external evaluator + Capability Maturity authority. **الفرق عن P12/R14:** هنا عقد منع التسرب والاستقلالية والتجميد قبل ظهور البيانات.

<a id="t09"></a>
## T09 — حزمة قبول لمختبر خارجي على جهاز نظيف

- **الحاجة:** قابلية إعادة التشغيل على جهاز المطور لا تعني أن مستخدمًا مستقلًا يستطيع تثبيت providers وفهم المخاطر وإعادة سجل النتائج.
- **مسار الجرد:** `src/engcore/engineering/bundle.py`، `src/engcore/providers/process.py`، `providers/`، `src/engcore/scientific/replay_core/` و`docs/flagships/`.
- **أصغر تجربة:** حزمة Beta محدودة Capability واحدة: frozen environment/lock، dataset مرخص، runbook، سؤال قابل للاختبار، مثال refusal، replay، SDK/API contract إن وجد، نموذج Feedback، وإشارة صريحة للحدود.
- **القبول:** مهندس خارج الفريق يتبع Runbook على جهاز نظيف، ويعيد حالة نجاح وحالة رفض، وتُسجل حالات setup fail أو missing provider كما هي؛ لا ادعاء Production Ready من pilot واحد.
- **المالك:** Product integration + reproducible provider env + pilot coordinator. **الفرق عن N10:** N10 ينقل bundle؛ هذا يقيس قابلية الاستخدام والفهم والتكرار *مستقلًا عن الفريق*.

<a id="t10"></a>
## T10 — حقوق إعادة الاستخدام وأدلة المشتري

- **الحاجة:** الاستحواذ أو نقل Pilot لشركة يتطلب إثبات مصدر الكود والبيانات وحدود تراخيص solver وdatasets وملفات العملاء، وليس فقط SHA للدليل العلمي.
- **مسار الجرد:** `pyproject.toml`، ملفات licenses في `providers/`، manifests للبيانات و`docs/architecture/`. **لا نستنتج ملكية أو حق إعادة توزيع من وجود ملف محلي.**
- **أصغر تجربة:** Software/Model/Data Bill of Materials لكل Pilot أو Capability؛ سجل المصدر والرخصة وشروط النقل والوصول والاحتفاظ وحالة consent للقياسات، مع استبعاد الأصول غير المصرح بتوزيعها.
- **القبول:** المشتري أو المختبر يعرف ما يمكن تشغيله ونقله والتعديل عليه قانونيًا؛ نقص تصريح dataset يوقف نشرها، لكنه لا يُصنَّف نقصًا علميًا ولا يُخفى من الحزمة.
- **المالك:** Packaging/legal review + data governance، دون تغيير physics أو scientific verdict. **الفرق عن N09:** N09 الاحتفاظ التقني بالملفات؛ هذا حقوق استخدامها وتوزيعها.

---

## مصفوفة التحويل إلى إثبات قابل للتدقيق (ليست backlog)

| المرحلة البحثية | بنود مؤثرة | Evidence artifact المطلوب | ما لا يُسمح باستنتاجه |
|---|---|---|---|
| Grounded scientific question | T01–T04 | زوج طلب صحيح/معدّل مع traces وقرار محفوظ | أن النص الحر مضمون الفهم لأي لغة |
| Honest scientific labeling | T05، T07 | V&V truth table، mutation failures، سجل النفي | أن Verification تعني Validation |
| SHA-bound assurance | T06، T07 | manifest current، gating evidence، independent review | أن القواعد المفروضة بالكود مفروضة بالضرورة في GitHub |
| External scientific proof | T08 | preregistration، sealed held-out results، leakage audit | أن تجربة واحدة تعمم على كل الدومينات |
| Independent pilot | T09–T10 | environment manifest، runbook، third-party feedback، data-use record | أن Pilot مجاني يعني عميلًا أو صفقة استحواذ |

## حدود التنفيذ وقرار المالك

- الوثيقة **لا تعدّل** `docs/work/ACTIVE_PLAN.md` ولا السياسة ولا capability ledger ولا claims/certificates. ترتيب التنفيذ الحالي الموثق: G0 ثم A1 ثم A2 ثم B1؛ لا يفرض هذا الملف Track إضافيًا.
- القيم الحالية لأي مشكلة يُعاد التحقق منها عند SHA التنفيذ؛ **NOT RUN** لكل السيناريوهات هنا. نتائج audit سابق عند SHA مختلف قرائن للبحث لا إثبات للحالة الجديدة.
- الأولوية البحثية المبدئية: T01/T02/T03/T05/T06/T07 ضمن G0 *إذا* اعتمد المالك أصغر slice؛ T08 بعد موافقة owner على بروتوكول مستقل ضمن حدود A1 والسياسة؛ T09/T10 استعداد تجاري غير مصرح ببدء Beta قبل إغلاق بوابات الأمان العلمي.
- قبل تحويل أي سطر إلى مهمة: (1) ربطه بمسار كود واختبار موجودين، (2) counterexample يعاد إنتاجه، (3) تكلفة وتبعات compatibility، (4) إثبات فشل اختبار guard قبل الإصلاح ونجاحه بعده، (5) مراجعة مستقلة إن مس claim/evidence/UQ/assurance، (6) owner approval عندما تمس الخطة أو recertification.
