/**
 * ENT MASTER — Core Application Script
 * Features:
 *  - Theme Toggle (Dark Pro & Clean Light) adhering to modern-web-guidance
 *  - Multilingual Engine (KK, RU, EN, UZ) with live DOM translation
 *  - Profile Subject Pair Selector
 *  - Interactive ENT Exam Simulator with Timer, Palette, and Score Calculation
 *  - Interactive Modals (Auth, Formula Sheet, Calculator, Mock Exam)
 */

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initLanguage();
  initProfileSelector();
  initMockExamSimulator();
  initAuthModal();
});

/* ==========================================================================
   1. Theme Management (Modern Web Guidance Compliant)
   ========================================================================== */
function initTheme() {
  const metaTheme = document.querySelector('meta[name="color-scheme"]');
  const storedTheme = localStorage.getItem('color-scheme');
  const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  // Initial resolution: stored theme or system preference
  const initialTheme = storedTheme || (systemPrefersDark ? 'dark' : 'dark'); // Dark Pro default for ENT Master
  applyTheme(initialTheme);

  // Bind toggle buttons
  const toggleBtns = document.querySelectorAll('.theme-toggle-btn');
  toggleBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
      const targetTheme = currentTheme === 'dark' ? 'light' : 'dark';
      
      localStorage.setItem('color-scheme', targetTheme);
      applyTheme(targetTheme);
    });
  });

  // Listen to system changes if no explicit override is pinned
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem('color-scheme')) {
      applyTheme(e.matches ? 'dark' : 'light');
    }
  });
}

function applyTheme(theme) {
  const metaTheme = document.querySelector('meta[name="color-scheme"]');
  if (metaTheme) {
    metaTheme.content = theme;
  }
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.setAttribute('data-bs-theme', theme);

  // Update theme icons
  const icons = document.querySelectorAll('.theme-toggle-icon');
  icons.forEach(icon => {
    if (theme === 'dark') {
      icon.className = 'bi bi-sun-fill theme-toggle-icon text-warning';
    } else {
      icon.className = 'bi bi-moon-stars-fill theme-toggle-icon text-primary';
    }
  });
}

/* ==========================================================================
   2. Multilingual Engine (KK, RU, EN, UZ)
   ========================================================================== */
let currentLang = 'kk';

function initLanguage() {
  const storedLang = localStorage.getItem('ent_lang') || 'kk';
  setLanguage(storedLang);

  const langLinks = document.querySelectorAll('[data-lang-choice]');
  langLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const chosenLang = link.getAttribute('data-lang-choice');
      setLanguage(chosenLang);
    });
  });
}

function setLanguage(lang) {
  if (!translations[lang]) lang = 'kk';
  currentLang = lang;
  localStorage.setItem('ent_lang', lang);

  // Update dropdown button label
  const langLabels = { kk: '🇰🇿 Қазақша', ru: '🇷🇺 Русский', en: '🇬🇧 English', uz: '🇺🇿 O\'zbekcha' };
  const currentLangLabelEl = document.getElementById('currentLangLabel');
  if (currentLangLabelEl) {
    currentLangLabelEl.textContent = langLabels[lang] || '🇰🇿 Қазақша';
  }

  // Update all [data-i18n] text elements
  const elements = document.querySelectorAll('[data-i18n]');
  elements.forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (translations[lang] && translations[lang][key]) {
      el.textContent = translations[lang][key];
    }
  });

  // Update placeholder attributes if any
  const inputs = document.querySelectorAll('[data-i18n-ph]');
  inputs.forEach(input => {
    const key = input.getAttribute('data-i18n-ph');
    if (translations[lang] && translations[lang][key]) {
      input.placeholder = translations[lang][key];
    }
  });
}

/* ==========================================================================
   3. Profile Subject Pair Selector
   ========================================================================== */
const profilePairs = {
  "math-phys": {
    kk: { p1: "Бейіндік 1: Математика", p1Desc: "Алгебра, функциялар, геометрия, интеграл және туындылар.", p2: "Бейіндік 2: Физика", p2Desc: "Механика, термодинамика, электромагнетизм, атомдық физика." },
    ru: { p1: "Профильный 1: Математика", p1Desc: "Алгебра, функции, геометрия, интегралы и производные.", p2: "Профильный 2: Физика", p2Desc: "Механика, термодинамика, электромагнетизм, кванты." },
    en: { p1: "Profile 1: Mathematics", p1Desc: "Advanced algebra, trigonometry, vectors, calculus & analysis.", p2: "Profile 2: Physics", p2Desc: "Newtonian mechanics, thermodynamics, electromagnetism, modern physics." },
    uz: { p1: "Mutaxassislik 1: Matematika", p1Desc: "Algebra, funksiyalar, geometriya, integral va hosilalar.", p2: "Mutaxassislik 2: Fizika", p2Desc: "Mexanika, termodinamika, elektromagnetizm, atom fizikasi." }
  },
  "bio-chem": {
    kk: { p1: "Бейіндік 1: Биология", p1Desc: "Генетика, цитология, адам анатомиясы, эволюция және экология.", p2: "Бейіндік 2: Химия", p2Desc: "Бейорганикалық, органикалық химия, реакция теңдеулері, есептер." },
    ru: { p1: "Профильный 1: Биология", p1Desc: "Генетика, цитология, анатомия человека, эволюция и экология.", p2: "Профильный 2: Химия", p2Desc: "Неорганическая и органическая химия, расчетные задачи." },
    en: { p1: "Profile 1: Biology", p1Desc: "Molecular genetics, cytology, human anatomy, ecosystems.", p2: "Profile 2: Chemistry", p2Desc: "Organic & inorganic synthesis, stoichiometry, molar reactions." },
    uz: { p1: "Mutaxassislik 1: Biologiya", p1Desc: "Genetika, sitologiya, odam anatomiyasi, ekologiya.", p2: "Mutaxassislik 2: Kimyo", p2Desc: "Anorganik va organik kimyo, reaksiyalar, masalalar." }
  },
  "geog-math": {
    kk: { p1: "Бейіндік 1: География", p1Desc: "Физикалық, экономикалық және әлеуметтік география, дүниежүзілік карталар.", p2: "Бейіндік 2: Математика", p2Desc: "Экономикалық есептер, ықтималдықтар теориясы, графиктер." },
    ru: { p1: "Профильный 1: География", p1Desc: "Физическая, экономическая и социальная география, номенклатура карт.", p2: "Профильный 2: Математика", p2Desc: "Экономические расчеты, теория вероятностей, графики." },
    en: { p1: "Profile 1: Geography", p1Desc: "Physical and socio-economic geography, world geospatial analysis.", p2: "Profile 2: Mathematics", p2Desc: "Financial math, probability theory, analytical geometry." },
    uz: { p1: "Mutaxassislik 1: Geografiya", p1Desc: "Tabiiy va iqtisodiy geografiya, jahon xaritalari.", p2: "Mutaxassislik 2: Matematika", p2Desc: "Iqtisodiy hisob-kitoblar, ehtimollar nazariyasi." }
  },
  "cs-math": {
    kk: { p1: "Бейіндік 1: Информатика", p1Desc: "Python бағдарламалау, деректер қоры (SQL), алгоритмдер, желілер.", p2: "Бейіндік 2: Математика", p2Desc: "Дискретті математика, логика, сандар жүйелері, матрицалар." },
    ru: { p1: "Профильный 1: Информатика", p1Desc: "Программирование на Python, базы данных SQL, алгоритмы, сети.", p2: "Профильный 2: Математика", p2Desc: "Дискретная математика, булева логика, системы счисления." },
    en: { p1: "Profile 1: Computer Science", p1Desc: "Python programming, relational SQL databases, networks, data structures.", p2: "Profile 2: Mathematics", p2Desc: "Discrete mathematics, mathematical logic, combinatorics." },
    uz: { p1: "Mutaxassislik 1: Informatika", p1Desc: "Python dasturlash, SQL ma'lumotlar bazasi, tarmoqlar.", p2: "Mutaxassislik 2: Matematika", p2Desc: "Diskret matematika, mantiq, hisoblash tizimlari." }
  }
};

function initProfileSelector() {
  const selector = document.getElementById('profilePairSelect');
  if (!selector) return;

  selector.addEventListener('change', (e) => {
    updateProfileCards(e.target.value);
  });
}

function updateProfileCards(pairKey) {
  const pairData = profilePairs[pairKey];
  if (!pairData) return;
  const langData = pairData[currentLang] || pairData['kk'];

  const p1Title = document.getElementById('prof1Title');
  const p1Desc = document.getElementById('prof1Desc');
  const p2Title = document.getElementById('prof2Title');
  const p2Desc = document.getElementById('prof2Desc');

  if (p1Title) p1Title.textContent = langData.p1;
  if (p1Desc) p1Desc.textContent = langData.p1Desc;
  if (p2Title) p2Title.textContent = langData.p2;
  if (p2Desc) p2Desc.textContent = langData.p2Desc;
}

/* ==========================================================================
   4. Interactive ENT Mock Exam Simulator Engine
   ========================================================================== */
const sampleExamQuestions = [
  {
    id: 1,
    subject: "Қазақстан тарихы",
    subject_ru: "История Казахстана",
    question: "1726 жылы қазақ жүздері өкілдерінің бас қосып, жоңғарларға қарсы ортақ майдан құру туралы шешім қабылдаған құрылтайы қай жерде өтті?",
    question_ru: "В каком месте в 1726 году состоялся всеказахский курултай, на котором было принято решение объединить силы против джунгаров?",
    options: [
      { key: "A", text: "Ордабасыда", text_ru: "В Ордабасы" },
      { key: "B", text: "Күлтөбеде", text_ru: "В Культобе" },
      { key: "C", text: "Қарақұмда", text_ru: "В Каракумах" },
      { key: "D", text: "Ұлытауда", text_ru: "В Улытау" },
      { key: "E", text: "Сарысу бойында", text_ru: "Вдоль реки Сарысу" }
    ],
    correct: "A"
  },
  {
    id: 2,
    subject: "Қазақстан тарихы",
    subject_ru: "История Казахстана",
    question: "«Жеті Жарғы» заңдар жинағын қабылдаған Қазақ хандығының билеушісі кім?",
    question_ru: "Какой хан Казахского ханства принял свод законов «Жеты Жаргы»?",
    options: [
      { key: "A", text: "Қасым хан", text_ru: "Касым хан" },
      { key: "B", text: "Тәуке хан", text_ru: "Тауке хан" },
      { key: "C", text: "Хақназар хан", text_ru: "Хакназар хан" },
      { key: "D", text: "Абылай хан", text_ru: "Абылай хан" },
      { key: "E", text: "Есім хан", text_ru: "Есим хан" }
    ],
    correct: "B"
  },
  {
    id: 3,
    subject: "Математикалық сауаттылық",
    subject_ru: "Мат. грамотность",
    question: "Дүкенде тауардың бағасы әуелі 20%-ға қымбаттап, кейін 20%-ға арзандатылды. Бастапқы баға қалай өзгерді?",
    question_ru: "Цена товара сначала увеличилась на 20%, а затем снизилась на 20%. Как изменилась первоначальная цена?",
    options: [
      { key: "A", text: "Өзгермеді", text_ru: "Не изменилась" },
      { key: "B", text: "4%-ға арзандады", text_ru: "Уменьшилась на 4%" },
      { key: "C", text: "4%-ға қымбаттады", text_ru: "Увеличилась на 4%" },
      { key: "D", text: "2%-ға арзандады", text_ru: "Уменьшилась на 2%" },
      { key: "E", text: "5%-ға арзандады", text_ru: "Уменьшилась на 5%" }
    ],
    correct: "B"
  },
  {
    id: 4,
    subject: "Математикалық сауаттылық",
    subject_ru: "Мат. грамотность",
    question: "Сағат 15:30 болғанда сағаттық және минуттық тілдердің арасындағы бұрыш неше градусқа тең?",
    question_ru: "Какой угол образуют часовая и минутная стрелки в 15:30?",
    options: [
      { key: "A", text: "90°", text_ru: "90°" },
      { key: "B", text: "85°", text_ru: "85°" },
      { key: "C", text: "75°", text_ru: "75°" },
      { key: "D", text: "60°", text_ru: "60°" },
      { key: "E", text: "105°", text_ru: "105°" }
    ],
    correct: "C"
  },
  {
    id: 5,
    subject: "Оқу сауаттылығы",
    subject_ru: "Грамотность чтения",
    question: "Мәтінде: «Жасанды интеллект адамның орнын толық алмастырмайды, ол тек оның мүмкіндіктерін еселейді» деген ой баяндалады. Автордың негізгі тұжырымы қандай?",
    question_ru: "В тексте утверждается: «ИИ не заменит человека полностью, а лишь расширит его возможности». Каков основной вывод автора?",
    options: [
      { key: "A", text: "ЖИ барлық мамандарды жұмыссыз қалдырады", text_ru: "ИИ приведет к тотальной безработице" },
      { key: "B", text: "ЖИ адаммен үйлесімді көмекші құрал ретінде қызмет етеді", text_ru: "ИИ является синергетическим инструментом для человека" },
      { key: "C", text: "ЖИ-ді қолдануға тыйым салу керек", text_ru: "Использование ИИ необходимо запретить" },
      { key: "D", text: "Адам интеллектісі өз күшін жоғалтты", text_ru: "Человеческий интеллект утратил значение" },
      { key: "E", text: "ЖИ тек ойын-сауыққа арналған", text_ru: "ИИ создан исключительно для развлечений" }
    ],
    correct: "B"
  },
  {
    id: 6,
    subject: "Математика (Бейіндік)",
    subject_ru: "Математика (Профиль)",
    question: "f(x) = 3x² - 12x + 7 функциясының туындысы нөлге тең болатын нүктені табыңыз:",
    question_ru: "Найдите точку, в которой производная функции f(x) = 3x² - 12x + 7 равна нулю:",
    options: [
      { key: "A", text: "x = 2", text_ru: "x = 2" },
      { key: "B", text: "x = -2", text_ru: "x = -2" },
      { key: "C", text: "x = 4", text_ru: "x = 4" },
      { key: "D", text: "x = 0", text_ru: "x = 0" },
      { key: "E", text: "x = 6", text_ru: "x = 6" }
    ],
    correct: "A"
  },
  {
    id: 7,
    subject: "Математика (Бейіндік)",
    subject_ru: "Математика (Профиль)",
    question: "Теңдеуді шешіңіз: log₂(x - 3) = 4",
    question_ru: "Решите уравнение: log₂(x - 3) = 4",
    options: [
      { key: "A", text: "19", text_ru: "19" },
      { key: "B", text: "11", text_ru: "11" },
      { key: "C", text: "16", text_ru: "16" },
      { key: "D", text: "35", text_ru: "35" },
      { key: "E", text: "7", text_ru: "7" }
    ],
    correct: "A"
  },
  {
    id: 8,
    subject: "Физика (Бейіндік)",
    subject_ru: "Физика (Профиль)",
    question: "Денеге әсер етуші теңәсерлі күш нөлге тең болса, дененің қозғалысы қандай болады?",
    question_ru: "Каким будет движение тела, если равнодействующая всех приложенных к нему сил равна нулю?",
    options: [
      { key: "A", text: "Тыныштықта тұрады немесе түзусызықты бірқалыпты қозғалады", text_ru: "Покоится или движется прямолинейно и равномерно" },
      { key: "B", text: "Бірқалыпты үдемелі қозғалады", text_ru: "Движется равноускоренно" },
      { key: "C", text: "Шеңбер бойымен қозғалады", text_ru: "Движется по окружности" },
      { key: "D", text: "Тез тоқтайды", text_ru: "Быстро останавливается" },
      { key: "E", text: "Еркін түседі", text_ru: "Свободно падает" }
    ],
    correct: "A"
  },
  {
    id: 9,
    subject: "Физика (Бейіндік)",
    subject_ru: "Физика (Профиль)",
    question: "Электр тізбегіндегі кернеу 220 В, ал кедергі 44 Ом болса, ток күші қандай?",
    question_ru: "Если напряжение в цепи равно 220 В, а сопротивление 44 Ом, какова сила тока?",
    options: [
      { key: "A", text: "5 А", text_ru: "5 А" },
      { key: "B", text: "9680 А", text_ru: "9680 А" },
      { key: "C", text: "0.2 А", text_ru: "0.2 А" },
      { key: "D", text: "10 А", text_ru: "10 А" },
      { key: "E", text: "2.5 А", text_ru: "2.5 А" }
    ],
    correct: "A"
  },
  {
    id: 10,
    subject: "Қазақстан тарихы",
    subject_ru: "История Казахстана",
    question: "Қазақстан Республикасының Тәуелсіздігі туралы Конституциялық Заң қашан қабылданды?",
    question_ru: "Когда был принят Конституционный закон о Государственной независимости Республики Казахстан?",
    options: [
      { key: "A", text: "1991 жыл 16 желтоқсан", text_ru: "16 декабря 1991 года" },
      { key: "B", text: "1990 жыл 25 қазан", text_ru: "25 октября 1990 года" },
      { key: "C", text: "1993 жыл 28 қаңтар", text_ru: "28 января 1993 года" },
      { key: "D", text: "1995 жыл 30 тамыз", text_ru: "30 августа 1995 года" },
      { key: "E", text: "1991 жыл 1 желтоқсан", text_ru: "1 декабря 1991 года" }
    ],
    correct: "A"
  }
];

let examState = {
  currentQuestionIndex: 0,
  userAnswers: {},
  flaggedQuestions: new Set(),
  secondsRemaining: 4 * 3600, // 240 mins official ENT
  timerInterval: null
};

function initMockExamSimulator() {
  // Render question palette
  renderExamPalette();
  loadQuestion(0);
  startExamTimer();

  // Flag button
  const flagBtn = document.getElementById('flagQuestionBtn');
  if (flagBtn) {
    flagBtn.addEventListener('click', toggleFlagCurrentQuestion);
  }

  // Next / Prev buttons
  const prevBtn = document.getElementById('examPrevBtn');
  const nextBtn = document.getElementById('examNextBtn');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (examState.currentQuestionIndex > 0) {
        loadQuestion(examState.currentQuestionIndex - 1);
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      if (examState.currentQuestionIndex < sampleExamQuestions.length - 1) {
        loadQuestion(examState.currentQuestionIndex + 1);
      }
    });
  }

  // Finish Exam Button
  const finishBtn = document.getElementById('finishExamBtn');
  if (finishBtn) {
    finishBtn.addEventListener('click', finishExamAndShowScore);
  }
}

function startExamTimer() {
  if (examState.timerInterval) clearInterval(examState.timerInterval);
  
  const timerDisplay = document.getElementById('liveExamTimer');
  if (!timerDisplay) return;

  examState.timerInterval = setInterval(() => {
    if (examState.secondsRemaining > 0) {
      examState.secondsRemaining--;
      const hours = Math.floor(examState.secondsRemaining / 3600);
      const minutes = Math.floor((examState.secondsRemaining % 3600) / 60);
      const seconds = examState.secondsRemaining % 60;
      timerDisplay.textContent = `${padZero(hours)}:${padZero(minutes)}:${padZero(seconds)}`;
    } else {
      clearInterval(examState.timerInterval);
      finishExamAndShowScore();
    }
  }, 1000);
}

function padZero(num) {
  return num < 10 ? '0' + num : num;
}

function renderExamPalette() {
  const container = document.getElementById('examQuestionPalette');
  if (!container) return;

  container.innerHTML = '';
  sampleExamQuestions.forEach((q, idx) => {
    const btn = document.createElement('button');
    btn.className = 'q-nav-pill';
    btn.id = `palette-btn-${idx}`;
    btn.textContent = idx + 1;
    btn.type = 'button';
    btn.title = `Сұрақ ${idx + 1}`;

    if (idx === examState.currentQuestionIndex) btn.classList.add('active');
    if (examState.userAnswers[idx]) btn.classList.add('answered');
    if (examState.flaggedQuestions.has(idx)) btn.classList.add('flagged');

    btn.addEventListener('click', () => loadQuestion(idx));
    container.appendChild(btn);
  });
}

function loadQuestion(index) {
  examState.currentQuestionIndex = index;
  const q = sampleExamQuestions[index];
  if (!q) return;

  // Update header text
  const numBadge = document.getElementById('examQNumber');
  const subjectBadge = document.getElementById('examQSubject');
  const questionText = document.getElementById('examQuestionText');
  const optionsContainer = document.getElementById('examOptionsContainer');

  const isRussian = currentLang === 'ru';

  if (numBadge) numBadge.textContent = `${isRussian ? 'Вопрос' : 'Сұрақ'} ${index + 1} / ${sampleExamQuestions.length}`;
  if (subjectBadge) subjectBadge.textContent = isRussian ? q.subject_ru : q.subject;
  if (questionText) questionText.textContent = isRussian ? q.question_ru : q.question;

  // Update flag button text/state
  const flagBtn = document.getElementById('flagQuestionBtn');
  if (flagBtn) {
    if (examState.flaggedQuestions.has(index)) {
      flagBtn.innerHTML = `<i class="bi bi-flag-fill text-warning"></i> ${isRussian ? 'Отмечен' : 'Белгіленген'}`;
      flagBtn.classList.add('btn-warning');
    } else {
      flagBtn.innerHTML = `<i class="bi bi-flag"></i> ${isRussian ? 'Белгілеу' : 'Белгі қою'}`;
      flagBtn.classList.remove('btn-warning');
    }
  }

  // Render options
  if (optionsContainer) {
    optionsContainer.innerHTML = '';
    q.options.forEach(opt => {
      const optionDiv = document.createElement('div');
      optionDiv.className = 'question-option-item';
      if (examState.userAnswers[index] === opt.key) {
        optionDiv.classList.add('selected');
      }

      optionDiv.innerHTML = `
        <span class="option-letter-badge">${opt.key}</span>
        <span class="option-text">${isRussian ? opt.text_ru : opt.text}</span>
      `;

      optionDiv.addEventListener('click', () => {
        selectOption(index, opt.key);
      });

      optionsContainer.appendChild(optionDiv);
    });
  }

  // Update palette active states
  sampleExamQuestions.forEach((_, idx) => {
    const pBtn = document.getElementById(`palette-btn-${idx}`);
    if (pBtn) {
      pBtn.classList.remove('active');
      if (idx === index) pBtn.classList.add('active');
    }
  });

  // Prev / Next button disable logic
  const prevBtn = document.getElementById('examPrevBtn');
  const nextBtn = document.getElementById('examNextBtn');
  if (prevBtn) prevBtn.disabled = index === 0;
  if (nextBtn) nextBtn.disabled = index === sampleExamQuestions.length - 1;
}

function selectOption(qIndex, optionKey) {
  examState.userAnswers[qIndex] = optionKey;
  
  // Update palette pill
  const pBtn = document.getElementById(`palette-btn-${qIndex}`);
  if (pBtn) pBtn.classList.add('answered');

  // Re-highlight options
  const options = document.querySelectorAll('.question-option-item');
  options.forEach(opt => {
    const key = opt.querySelector('.option-letter-badge').textContent.trim();
    if (key === optionKey) {
      opt.classList.add('selected');
    } else {
      opt.classList.remove('selected');
    }
  });

  // Auto save visual pulse
  const saveIndicator = document.getElementById('autoSaveIndicator');
  if (saveIndicator) {
    saveIndicator.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i> Сақталды`;
    setTimeout(() => {
      saveIndicator.innerHTML = `<i class="bi bi-cloud-check"></i> Авто-сақтау қосулы`;
    }, 1200);
  }
}

function toggleFlagCurrentQuestion() {
  const index = examState.currentQuestionIndex;
  if (examState.flaggedQuestions.has(index)) {
    examState.flaggedQuestions.delete(index);
  } else {
    examState.flaggedQuestions.add(index);
  }
  renderExamPalette();
  loadQuestion(index);
}

function finishExamAndShowScore() {
  let correctCount = 0;
  sampleExamQuestions.forEach((q, idx) => {
    if (examState.userAnswers[idx] === q.correct) {
      correctCount++;
    }
  });

  // Calculate simulated 140 scale score based on answered accuracy
  const total = sampleExamQuestions.length;
  const percentage = Math.round((correctCount / total) * 100);
  const simulatedEntScore = Math.round((correctCount / total) * 140);

  // Populate Score Modal
  const scoreModalEl = document.getElementById('examResultModal');
  if (scoreModalEl) {
    document.getElementById('resScoreTotal').textContent = `${simulatedEntScore} / 140`;
    document.getElementById('resAccuracy').textContent = `${percentage}% (${correctCount}/${total})`;
    
    const feedbackEl = document.getElementById('resFeedbackMsg');
    if (feedbackEl) {
      if (simulatedEntScore >= 120) {
        feedbackEl.textContent = "🏆 Керемет нәтиже! Мемлекеттік грант алу мүмкіндігіңіз өте жоғары (98%+)!";
      } else if (simulatedEntScore >= 100) {
        feedbackEl.textContent = "👍 Жақсы нәтиже! Біраз әлсіз тақырыптарды пысықтасаңыз, грант сіздікі!";
      } else {
        feedbackEl.textContent = "📚 Дайындықты күшейту қажет. ENT MASTER курстары арқылы баллыңызды көтеріңіз!";
      }
    }

    const modal = new bootstrap.Modal(scoreModalEl);
    modal.show();
  }
}

/* ==========================================================================
   5. Authentication Modal Toggling
   ========================================================================== */
function initAuthModal() {
  const loginTabBtn = document.getElementById('authLoginTab');
  const registerTabBtn = document.getElementById('authRegisterTab');
  const loginForm = document.getElementById('authLoginForm');
  const registerForm = document.getElementById('authRegisterForm');

  if (loginTabBtn && registerTabBtn && loginForm && registerForm) {
    loginTabBtn.addEventListener('click', () => {
      loginTabBtn.classList.add('active', 'btn-primary-gradient');
      loginTabBtn.classList.remove('btn-secondary-glass');
      registerTabBtn.classList.remove('active', 'btn-primary-gradient');
      registerTabBtn.classList.add('btn-secondary-glass');
      loginForm.classList.remove('d-none');
      registerForm.classList.add('d-none');
    });

    registerTabBtn.addEventListener('click', () => {
      registerTabBtn.classList.add('active', 'btn-primary-gradient');
      registerTabBtn.classList.remove('btn-secondary-glass');
      loginTabBtn.classList.remove('active', 'btn-primary-gradient');
      loginTabBtn.classList.add('btn-secondary-glass');
      registerForm.classList.remove('d-none');
      loginForm.classList.add('d-none');
    });
  }

  // Demo alert for login/register submission
  const authSubmitButtons = document.querySelectorAll('.auth-submit-btn');
  authSubmitButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      // Redirect or open student dashboard
      window.location.href = 'dashboard.html';
    });
  });
}
