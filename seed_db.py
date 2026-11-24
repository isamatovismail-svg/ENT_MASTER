"""
ENT MASTER — Database Initial Data Seeder.
Populates standard subjects, allowed profile combinations, sample approved questions,
default exam configuration, and test demo users.
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import User
from subjects.models import Subject, ProfileSubjectCombination, StudentSubjectSelection
from questions.models import Question, AnswerOption
from exams.models import ExamConfiguration

def seed_data():
    print("🌱 Seeding ENT MASTER platform database...")

    # 1. Administrator Account
    admin_user, created = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@entmaster.kz',
            'first_name': 'Администратор',
            'last_name': 'Платформы',
            'role': User.Role.ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'is_teacher_approved': True,
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print("  ✓ Created Admin user: admin / admin123")

    # 2. Approved Teacher Account
    teacher_user, created = User.objects.get_or_create(
        username='teacher',
        defaults={
            'email': 'teacher@entmaster.kz',
            'first_name': 'Асқар',
            'last_name': 'Жұмабаев',
            'role': User.Role.TEACHER,
            'is_staff': True,
            'is_teacher_approved': True,
            'phone': '+7 701 555 4433',
        }
    )
    if created:
        teacher_user.set_password('teacher123')
        teacher_user.save()
        print("  ✓ Created Teacher user: teacher / teacher123")

    # 3. Student Account
    student_user, created = User.objects.get_or_create(
        username='student',
        defaults={
            'email': 'aidos@student.kz',
            'first_name': 'Айдос',
            'last_name': 'Тұрсынбай',
            'role': User.Role.STUDENT,
            'target_university': 'Әл-Фараби атындағы ҚазҰУ',
            'target_score': 132,
            'phone': '+7 777 123 4567',
            'is_teacher_approved': True,
        }
    )
    if created:
        student_user.set_password('student123')
        student_user.save()
        print("  ✓ Created Student user: student / student123")

    # 4. Standard Subjects
    subjects_data = [
        # 3 Compulsory Subjects
        {
            'code': 'KZ_HISTORY',
            'name': 'Қазақстан тарихы',
            'name_kk': 'Қазақстан тарихы',
            'name_ru': 'История Казахстана',
            'name_en': 'Kazakhstan History',
            'name_uz': "Qozog'iston tarixi",
            'is_compulsory': True,
            'icon_class': 'bi-landmark-fill',
            'default_question_count': 20,
            'max_score': 20,
            'order': 1,
            'description': 'Ежелгі дәуірден бүгінгі күнге дейінгі кезеңдер, хронологиялық кестелер мен карталар.'
        },
        {
            'code': 'MATH_LIT',
            'name': 'Математикалық сауаттылық',
            'name_kk': 'Математикалық сауаттылық',
            'name_ru': 'Математическая грамотность',
            'name_en': 'Mathematical Literacy',
            'name_uz': 'Matematik savodxonlik',
            'is_compulsory': True,
            'icon_class': 'bi-calculator-fill',
            'default_question_count': 15,
            'max_score': 15,
            'order': 2,
            'description': 'Логика, диаграммалар мен графиктерді талдау, практикалық есептерді шешу алгоритмдері.'
        },
        {
            'code': 'READ_LIT',
            'name': 'Оқу сауаттылығы',
            'name_kk': 'Оқу сауаттылығы',
            'name_ru': 'Грамотность чтения',
            'name_en': 'Reading Literacy',
            'name_uz': "O'qish savodxonligi",
            'is_compulsory': True,
            'icon_class': 'bi-book-half',
            'default_question_count': 15,
            'max_score': 15,
            'order': 3,
            'description': 'Күрделі мәтіндермен жұмыс, тұжырым жасау, идея мен автор көзқарасын анықтау.'
        },
        # Profile Elective Subjects
        {
            'code': 'MATH',
            'name': 'Математика',
            'name_kk': 'Математика (Бейіндік)',
            'name_ru': 'Математика (Профильная)',
            'name_en': 'Mathematics (Profile)',
            'name_uz': 'Matematika (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-infinity',
            'default_question_count': 35,
            'max_score': 45,
            'order': 4,
            'description': 'Алгебра, тригонометрия, планиметрия, стереометрия, функциялар мен туындылар.'
        },
        {
            'code': 'PHYSICS',
            'name': 'Физика',
            'name_kk': 'Физика (Бейіндік)',
            'name_ru': 'Физика (Профильная)',
            'name_en': 'Physics (Profile)',
            'name_uz': 'Fizika (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-lightning-charge-fill',
            'default_question_count': 35,
            'max_score': 45,
            'order': 5,
            'description': 'Механика, термодинамика, электродинамика, кванттық және атомдық физика.'
        },
        {
            'code': 'CHEMISTRY',
            'name': 'Химия',
            'name_kk': 'Химия (Бейіндік)',
            'name_ru': 'Химия (Профильная)',
            'name_en': 'Chemistry (Profile)',
            'name_uz': 'Kimyo (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-droplet-fill',
            'default_question_count': 35,
            'max_score': 45,
            'order': 6,
            'description': 'Бейорганикалық және органикалық химия, реакция теңдеулері, есептер.'
        },
        {
            'code': 'BIOLOGY',
            'name': 'Биология',
            'name_kk': 'Биология (Бейіндік)',
            'name_ru': 'Биология (Профильная)',
            'name_en': 'Biology (Profile)',
            'name_uz': 'Biologiya (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-tree-fill',
            'default_question_count': 35,
            'max_score': 45,
            'order': 7,
            'description': 'Цитология, генетика, адам анатомиясы, эволюция және экология.'
        },
        {
            'code': 'GEOGRAPHY',
            'name': 'География',
            'name_kk': 'География (Бейіндік)',
            'name_ru': 'География (Профильная)',
            'name_en': 'Geography (Profile)',
            'name_uz': 'Geografiya (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-globe-americas',
            'default_question_count': 35,
            'max_score': 45,
            'order': 8,
            'description': 'Физикалық, экономикалық және әлеуметтік география, номенклатура.'
        },
        {
            'code': 'WORLD_HISTORY',
            'name': 'Дүниежүзі тарихы',
            'name_kk': 'Дүниежүзі тарихы (Бейіндік)',
            'name_ru': 'Всемирная история (Профильная)',
            'name_en': 'World History (Profile)',
            'name_uz': 'Jahon tarixi (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-hourglass-split',
            'default_question_count': 35,
            'max_score': 45,
            'order': 9,
            'description': 'Ежелгі дүние, орта ғасырлар, жаңа және қазіргі заман тарихы.'
        },
        {
            'code': 'LAW',
            'name': 'Құқық негіздері',
            'name_kk': 'Құқық негіздері (Бейіндік)',
            'name_ru': 'Основы права (Профильная)',
            'name_en': 'Law Fundamentals (Profile)',
            'name_uz': 'Huquq asoslari (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-shield-check',
            'default_question_count': 35,
            'max_score': 45,
            'order': 10,
            'description': 'ҚР Конституциялық құқығы, азаматтық, әкімшілік және қылмыстық құқық.'
        },
        {
            'code': 'INFORMATICS',
            'name': 'Информатика',
            'name_kk': 'Информатика (Бейіндік)',
            'name_ru': 'Информатика (Профильная)',
            'name_en': 'Informatics / CS (Profile)',
            'name_uz': 'Informatika (Mutaxassislik)',
            'is_compulsory': False,
            'icon_class': 'bi-cpu-fill',
            'default_question_count': 35,
            'max_score': 45,
            'order': 11,
            'description': 'Python бағдарламалау, деректер қоры (SQL), алгоритмдер, желілер.'
        },
    ]

    subject_map = {}
    for s_data in subjects_data:
        subj, _ = Subject.objects.update_or_create(code=s_data['code'], defaults=s_data)
        subject_map[s_data['code']] = subj
    print(f"  ✓ Created/Updated {len(subjects_data)} subjects.")

    # 5. Allowed Profile Combinations
    combinations_data = [
        ('MATH', 'PHYSICS', 'Математика + Физика (Инженерия & IT)'),
        ('BIOLOGY', 'CHEMISTRY', 'Биология + Химия (Медицина & Фармация)'),
        ('GEOGRAPHY', 'MATH', 'География + Математика (Экономика & Логистика)'),
        ('INFORMATICS', 'MATH', 'Информатика + Математика (Киберқауіпсіздік & AI)'),
        ('WORLD_HISTORY', 'LAW', 'Дүниежүзі тарихы + Құқық негіздері (Заңгерлік)'),
        ('GEOGRAPHY', 'BIOLOGY', 'География + Биология (Экология & Ауыл шаруашылығы)'),
    ]

    for s1_code, s2_code, comb_name in combinations_data:
        s1 = subject_map.get(s1_code)
        s2 = subject_map.get(s2_code)
        if s1 and s2:
            comb, _ = ProfileSubjectCombination.objects.get_or_create(
                subject_1=s1,
                subject_2=s2,
                defaults={'name': comb_name, 'is_active': True}
            )

    print(f"  ✓ Created {len(combinations_data)} allowed profile subject pairs.")

    # 6. Assign Default Subject Pair to Student User
    default_comb = ProfileSubjectCombination.objects.filter(subject_1__code='MATH', subject_2__code='PHYSICS').first()
    if default_comb and student_user:
        StudentSubjectSelection.objects.get_or_create(
            student=student_user,
            defaults={'combination': default_comb}
        )
        print("  ✓ Assigned 'Math + Physics' pair to demo student user.")

    # 7. Default Exam Configuration
    ExamConfiguration.objects.get_or_create(
        is_active=True,
        defaults={
            'title': 'ҰБТ 2026-2027 Ресми Симуляторы',
            'duration_minutes': 240,
            'total_questions': 120,
            'total_max_score': 140,
            'compulsory_history_count': 20,
            'compulsory_mathlit_count': 15,
            'compulsory_readlit_count': 15,
            'profile_1_count': 35,
            'profile_2_count': 35
        }
    )
    print("  ✓ Created default active ExamConfiguration.")

    # 8. Sample High-Quality Approved Questions with Explanations
    sample_questions = [
        # Kazakhstan History
        {
            'subject_code': 'KZ_HISTORY',
            'type': Question.QuestionType.SINGLE,
            'text': '1726 жылы қазақ үш жүзінің өкілдері жиналып, жоңғарларға қарсы біріккен ортақ майдан құру туралы шешім қабылдаған құрылтай қай жерде өтті?',
            'explanation': '1726 жылы Ордабасы тауында өткен құрылтайда қазақ жасақтарының бас қолбасшысы болып Әбілқайыр хан сайланып, жоңғар басқыншыларына қарсы бүкілқазақтық одақ құрылды.',
            'options': [
                ('A', 'Ордабасы тауында', True),
                ('B', 'Күлтөбеде', False),
                ('C', 'Қарақұмда', False),
                ('D', 'Ұлытауда', False),
                ('E', 'Сарысу бойында', False)
            ]
        },
        {
            'subject_code': 'KZ_HISTORY',
            'type': Question.QuestionType.SINGLE,
            'text': '«Жеті Жарғы» заңдар жинағын қабылдап, Қазақ хандығының ішкі бірлігін күшейткен хан кім?',
            'explanation': 'XVII ғасырдың соңында Тәуке хан атақты Төле, Қазыбек және Әйтеке билердің қатысуымен «Жеті Жарғы» заңдар жинағын енгізді.',
            'options': [
                ('A', 'Қасым хан', False),
                ('B', 'Тәуке хан', True),
                ('C', 'Хақназар хан', False),
                ('D', 'Абылай хан', False),
                ('E', 'Есім хан', False)
            ]
        },
        {
            'subject_code': 'KZ_HISTORY',
            'type': Question.QuestionType.SINGLE,
            'text': 'Қазақстан Республикасының Мемлекеттік Тәуелсіздігі туралы Конституциялық Заң қабылданған тарихи күн:',
            'explanation': '1991 жылдың 16 желтоқсанында Жоғарғы Кеңес ҚР Мемлекеттік Тәуелсіздігі туралы тарихи Конституциялық Заңды қабылдады.',
            'options': [
                ('A', '1991 жыл 16 желтоқсан', True),
                ('B', '1990 жыл 25 қазан', False),
                ('C', '1993 жыл 28 қаңтар', False),
                ('D', '1995 жыл 30 тамыз', False),
                ('E', '1991 жыл 1 желтоқсан', False)
            ]
        },
        # Mathematical Literacy
        {
            'subject_code': 'MATH_LIT',
            'type': Question.QuestionType.SINGLE,
            'text': 'Дүкенде тауардың бағасы әуелі 20%-ға қымбаттап, кейін 20%-ға арзандатылды. Бастапқы баға қалай өзгерді?',
            'explanation': 'Бастапқы баға 100 болсын. 20% қымбаттаған соң: 120 болды. 120-ның 20%-ы: 24. Арзандаған соң: 120 - 24 = 96. Демек баға 4%-ға арзандады.',
            'options': [
                ('A', 'Өзгермеді', False),
                ('B', '4%-ға арзандады', True),
                ('C', '4%-ға қымбаттады', False),
                ('D', '2%-ға арзандады', False),
                ('E', '5%-ға арзандады', False)
            ]
        },
        {
            'subject_code': 'MATH_LIT',
            'type': Question.QuestionType.SINGLE,
            'text': 'Сағат 15:30-ды көрсетіп тұрғанда, сағаттық және минуттық тілдер арасындағы кіші бұрыш неше градусқа тең?',
            'explanation': 'Әр сағат бөлігі 30°. Сағат 3:30 болғанда сағат тілі 3 пен 4-тің дәл ортасында (яғни 3.5), ал минут тілі 6-да. Арақашықтық: 2.5 бөлік * 30° = 75°.',
            'options': [
                ('A', '90°', False),
                ('B', '85°', False),
                ('C', '75°', True),
                ('D', '60°', False),
                ('E', '105°', False)
            ]
        },
        # Reading Literacy
        {
            'subject_code': 'READ_LIT',
            'type': Question.QuestionType.SINGLE,
            'text': 'Мәтінде: «Жасанды интеллект адамның орнын толық баспайды, ол тек оның шығармашылық және кәсіби мүмкіндіктерін еселейтін қуатты құрал» делінген. Автордың негізгі идеясы қандай?',
            'explanation': 'Автор жасанды интеллект адамды ығыстырмайды, керісінше онымен серіктес тиімді құрал ретінде қызмет ететінін атап көрсетеді.',
            'options': [
                ('A', 'ЖИ барлық мамандарды жұмыссыз қалдырады', False),
                ('B', 'ЖИ адамға көмекші және мүмкіндікті арттырушы серіктес құрал', True),
                ('C', 'ЖИ-ді қолдануға тыйым салу керек', False),
                ('D', 'Адам интеллектісі өз маңызын жоғалтты', False),
                ('E', 'ЖИ тек сандық есептер шығаруға арналған', False)
            ]
        },
        # Profile Math
        {
            'subject_code': 'MATH',
            'type': Question.QuestionType.SINGLE,
            'text': 'f(x) = 3x² - 12x + 7 функциясының туындысы нөлге тең болатын нүктені (стационар нүктені) табыңыз:',
            'explanation': "f'(x) = 6x - 12. f'(x) = 0 теңдеуінен: 6x = 12 => x = 2.",
            'options': [
                ('A', 'x = 2', True),
                ('B', 'x = -2', False),
                ('C', 'x = 4', False),
                ('D', 'x = 0', False),
                ('E', 'x = 6', False)
            ]
        },
        {
            'subject_code': 'MATH',
            'type': Question.QuestionType.SINGLE,
            'text': 'Теңдеуді шешіңіз: log₂(x - 3) = 4',
            'explanation': 'Логарифм анықтамасы бойынша: x - 3 = 2⁴ = 16 => x = 16 + 3 = 19.',
            'options': [
                ('A', '19', True),
                ('B', '11', False),
                ('C', '16', False),
                ('D', '35', False),
                ('E', '7', False)
            ]
        },
        # Profile Physics
        {
            'subject_code': 'PHYSICS',
            'type': Question.QuestionType.SINGLE,
            'text': 'Денеге әсер етуші барлық күштердің теңәсерлі күші нөлге тең болса, дененің қозғалыс күйі қандай болады?',
            'explanation': 'Ньютонның 1-заңы бойынша: егер сыртқы күштер әсер етпесе немесе олар теңгерілсе, дене тыныштық күйін сақтайды немесе түзусызықты бірқалыпты қозғалады.',
            'options': [
                ('A', 'Тыныштықта тұрады немесе түзусызықты бірқалыпты қозғалады', True),
                ('B', 'Бірқалыпты үдемелі қозғалады', False),
                ('C', 'Шеңбер бойымен бірқалыпты қозғалады', False),
                ('D', 'Лезде тоқтайды', False),
                ('E', 'Еркін құлайды', False)
            ]
        },
        {
            'subject_code': 'PHYSICS',
            'type': Question.QuestionType.SINGLE,
            'text': 'Электр тізбегіндегі кернеу 220 В, ал кедергі 44 Ом болса, тізбектен өтетін ток күші қандай?',
            'explanation': 'Тізбек бөлігіне арналған Ом заңы бойынша: I = U / R = 220 / 44 = 5 А.',
            'options': [
                ('A', '5 А', True),
                ('B', '9680 А', False),
                ('C', '0.2 А', False),
                ('D', '10 А', False),
                ('E', '2.5 А', False)
            ]
        },
        # Multiple Choice Question Example
        {
            'subject_code': 'MATH',
            'type': Question.QuestionType.MULTIPLE,
            'text': 'х² - 5х + 6 = 0 квадрат теңдеуінің түбірлерін және олардың қосындысын табыңыз:',
            'explanation': 'Виет теоремасы бойынша: түбірлер x₁=2, x₂=3. Түбірлер қосындысы: 2 + 3 = 5.',
            'options': [
                ('A', '2', True),
                ('B', '3', True),
                ('C', '5 (қосындысы)', True),
                ('D', '-2', False),
                ('E', '-3', False),
                ('F', '6', False)
            ]
        }
    ]

    for q_data in sample_questions:
        subj = subject_map.get(q_data['subject_code'])
        if not subj:
            continue

        q, _ = Question.objects.get_or_create(
            subject=subj,
            text=q_data['text'],
            defaults={
                'question_type': q_data['type'],
                'difficulty': Question.Difficulty.MEDIUM,
                'language': Question.Language.KK,
                'explanation': q_data['explanation'],
                'moderation_status': Question.ModerationStatus.APPROVED,
                'created_by': teacher_user,
                'points': 2 if q_data['type'] == Question.QuestionType.MULTIPLE else 1
            }
        )

        for key, text, is_correct in q_data['options']:
            AnswerOption.objects.get_or_create(
                question=q,
                key=key,
                defaults={'text': text, 'is_correct': is_correct}
            )

    print(f"  ✓ Seeded {len(sample_questions)} approved questions across subjects.")
    print("✨ Database seeding completed successfully!")

if __name__ == '__main__':
    seed_data()
