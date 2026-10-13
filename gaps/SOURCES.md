# المصادر وحدود الحالة الحالية

## مراجعة إضافية بعد PR #136

ملف [الفجوات الإضافية](06-additional-cross-cutting-gaps.md) مبني على قراءة ساكنة عند `375ab559677768dec5ab2c7267f20d127f51b197` بتاريخ 2026-10-14. كل بند يربط بمصدره المباشر، ويذكر القدرة الموجودة قبل اقتراح التوسيع. المراجع الجديدة تشمل سياسة النضج وreplay migration/profiles وevidence supersession ومشغلات الرصد وعقود graph/plan وتخزين البيانات. لم ننفذ أمثلة مضادة علمية أو نستنتج غياب القدرة من مجرد غياب اختبار مقروء.

## خط الأساس

المحادثة بدأت من checkout عند `a3f757eb5fdbc804ef11e3c4088a757c31981870`. PR الوثائق يبدأ من `5d73e8f5118aa845f1957decc5aae986e72476a9`. قرأنا تاريخ التقدم وبعض الملفات المتأثرة، ولم نراجع كل الإصلاحات بينهما أو نعد تشغيل الأمثلة السابقة.

التاريخ: 2026-10-14. الوثائق الحالية والخطة لا تعطي حقًا لتحويل هذه الاقتراحات إلى مسار عمل موازٍ.

## خريطة الملكية والمصادر المحلية

| الموضوع | الملفات المرجعية | استخدام المصدر |
|---|---|---|
| الاتجاه والتنفيذ | [Master Plan](../docs/project/FORGE_MASTER_PLAN.md)، [Active Plan](../docs/work/ACTIVE_PLAN.md) | اختيار العمل الحالي لا إثبات نجاحه |
| العقود والطبقات | [Architecture](../docs/architecture/README.md)، [Freeze](../docs/CORE_FREEZE_POLICY.md) | ملكية وتوافق؛ لا إعادة تصميم عشوائية |
| المطالب والأدلة | [Intelligence](../docs/scientific-core/scientific-intelligence-layer.md) | إعادة استخدام المسارات الحالية |
| النقل والاتزان | [mapping.py](../src/engcore/execution/multiphysics/mapping.py)، [runtime.py](../src/engcore/execution/multiphysics/runtime.py) | C05–C06 وR03 وR07–R08 |
| التقارب والتسريع | [convergence.py](../src/engcore/execution/multiphysics/convergence.py)، [relaxation.py](../src/engcore/execution/multiphysics/relaxation.py) | التقارب وAitken موجودان |
| تفسير خطأ الربط | [error.py](../src/engcore/execution/multiphysics/error.py) | ملاحظة R02 تحتاج إثباتًا رياضيًا وتجريبيًا |
| preCICE | [adapter](../providers/precice/forge_precice/__init__.py)، [driver](../providers/precice/forge_precice/driver.py) | جرد التكامل قبل توسيعه |
| الحالة وتعدد الأزمنة | [adapters](../src/engcore/coupling/adapters.py)، [multiscale](../src/engcore/multiscale/runtime.py) | قدرات موجودة لا تعاد من الصفر |
| تشغيل موحد | [system runtime](../docs/architecture/system_runtime.md) | preflight، tracing، checkpoints، الهوية |
| الهوية والعمليات | [catalog](../src/engcore/providers/catalog.py)، [process](../src/engcore/providers/process.py) | الهوية وtimeouts والفشل |
| واجهة المنتج | [capabilities](../src/engcore/product/capabilities.py)، [runtime](../src/engcore/product/runtime.py) | القوالب والمدخلات والقدرات |
| القياسات والتشخيص | [measurement dataset](../src/engcore/claims/measurement_dataset.py)، [diagnostics](../src/engcore/claims/analysis/diagnostics.py) | واجهات فوق سجلات قائمة |
| التقارير | [engineering](../docs/architecture/engineering.md)، [flagships](../docs/flagships/README.md) | لا تخلق حكمًا علميًا جديدًا |
| التاريخ والنتائج | [PROGRESS](../docs/work/PROGRESS.md) | نتائج تاريخية مرتبطة بأوامرها وسياقها |

## تصحيح حالة البنود التاريخية

- **هوية providers:** ملف catalog الحالي يتضمن منطقًا أوسع لمحتوى التوزيعات وRECORD وeditable installs. وصف البحث القديم بأن الهوية مجرد metadata لا يجوز تعميمه على HEAD الحالي. R05 يتطلب اختبار الحماية الحالية أولًا.
- **timeouts وميزانيات التشغيل:** تاريخ main يحتوي `a1cc7bf6` لمعالجة probes/timeouts، و`ce96fa06` لمعالجة sweep budgets وغيرها. P09 وG14 توسيع أو تقييم، لا ادعاء غياب.
- **الدراسات:** يوجد `src/engcore/execution/sweep.py`؛ P04 وG10 يقترحان تقوية الواجهة والاتساق لا محرك sweep جديدًا.
- **اختبارات الأداء:** main يحتوي PRs #134 و#135، وخيارات forge_check --dev / --scientific وقياسات زمنية وتحسينات عزل. أرقام البحث القديم ليست baseline حاليًا.
- **واجهات البطارية:** تاريخ main يحتوي أعمالًا أحدث من البحث المحلي؛ لا تعتبر قائمة المسارات القديمة جردًا كاملًا للقدرات الحالية.
- **CI:** الملف المقروء [Tests](../.github/workflows/tests.yml) يحتوي workflow_dispatch فقط عند هذا الأساس. عقد المستخدم في هذه المهمة يطلب PR/push gates آلية. هذا اختلاف مسجل، لا إذن لإضعاف العقد أو تعديل CI في PR وثائق. لا ندعي مرور فحوص GitHub تلقائية.
- **الخطة:** BIG 14/15 توصيف تاريخي من checkout الأول. الخطة المقروءة حديثًا هي G0 → A1 → A2 → B1. لم نغيرها.

## مراجع خارجية رسمية

| المرجع | ما يدعمه |
|---|---|
| [preCICE mapping](https://precice.org/configuration-mapping) | الفرق بين consistent وconservative وscaled-consistent؛ لا يكفي حفظ الإجمالي لإثبات دقة محلية |
| [preCICE acceleration](https://precice.org/configuration-acceleration) | Aitken وIQN-ILS وIQN-IMVJ؛ تحسين الأداء يحتاج قياسًا على الحالة |
| [preCICE coupling](https://precice.org/configuration-coupling) | شروط تقارب الربط وتسجيلها |
| [preCICE waveform](https://precice.org/couple-your-code-waveform) | تبادل بيانات زمنية وخطوات غير متطابقة؛ تحقق من الإصدار والخيارات عند التنفيذ |
| [preCICE visualization](https://precice.org/tooling-config-visualization) | رسم تكوين الربط لتسهيل المراجعة |
| [preCICE system tests](https://precice.org/dev-docs-system-tests) | اختبار تراكيب ذات إصدارات محددة |
| [MOOSE MultiApps](https://mooseframework.inl.gov/syntax/MultiApps/index.html) | ترتيب التطبيقات والنقل وربط fixed-point؛ ليس طلبًا لتغيير محرك Forge |
| [SUNDIALS ARKODE](https://sundials.readthedocs.io/en/latest/arkode/Introduction_link.html) | تكامل متعدد الأزمنة؛ إعادة استخدام provider مناسب بدل كتابة solver جديد |
| [NASA grid convergence](https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html) | دراسة خطأ التقسيم العددي؛ ليست validation تجريبيًا |
| [PyBaMM experiments](https://docs.pybamm.org/en/pybamm-v26.10.0.0/source/examples/notebooks/getting_started/tutorial-5-run-experiments.html) | تجارب وملفات حمل زمنية |
| [PyBaMM parameterisation](https://docs.pybamm.org/en/pybamm-v26.10.0.0/source/examples/notebooks/parameterization/parameterization.html) | تحديد معاملات النموذج؛ لا يثبت الانطباق على أي خلية |
| [OpenMDAO recording](https://openmdao.org/newdocs/versions/latest/features/recording/driver_recording.html) | تسجيل المتغيرات والأهداف والقيود للمقارنات |

المراجع اطلع عليها أثناء البحث في المحادثة؛ لا تعني أنها مستخدمة أو مختبرة بإصداراتها في Forge. لا توجد وعود أداء أو دقة مشتقة من مجرد وجود ميزة في مكتبة خارجية.
