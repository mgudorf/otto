from app.modules import Agent, Manifest

MANIFEST = Manifest(
    name="education",
    title="Education",
    hue="#7a9fd6",
    icon='<path d="M2 8l8-4 8 4-8 4-8-4Z"></path><path d="M6 10v4c0 1.2 2 2 4 2s4-.8 4-2v-4"></path><path d="M18 8v5"></path>',
    order=2,
    agent=Agent(
        placeholder="Ask the tutor…",
        skills=("question-gen", "quiz", "explain", "plan"),
        read_tools=("education_topics", "education_questions", "education_question", "education_feedback"),
        write_tools=("education_add_topic", "education_add_question", "education_grade", "education_record_feedback"),
    ),
)
