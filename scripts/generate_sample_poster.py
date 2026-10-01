from __future__ import annotations

from pathlib import Path

from tbos_renderer.content_engine.schemas import (
    CaptionPack,
    ContentLanguage,
    ContentMetadata,
    ContentType,
    Difficulty,
    FactSensitivity,
    HashtagPack,
    PosterContent,
    PracticeQuestion,
)
from tbos_renderer.rendering.poster import PosterRenderer


def create_sample_list_vs_tuple_poster() -> PosterContent:
    metadata = ContentMetadata(
        brand="TechBuilt Open School",
        content_type=ContentType.POSTER,
        language=ContentLanguage.ROMAN_URDU,
        content_pillar="Python & Data Structures",
        topic="Python List vs Tuple",
        target_audience="Beginner to intermediate Python developers",
        objective="Understand mutability and memory differences",
        tone="practical, clear, authoritative",
        difficulty=Difficulty.BEGINNER,
        cta_type="save",
        fact_sensitivity=FactSensitivity.LOW,
        prompt_template_name="poster_developer",
        prompt_template_version=2,
        model_name="gemini-2.5-flash",
        generation_parameters={},
        content_hash="c" * 64,
        quality_score=96,
    )
    return PosterContent(
        metadata=metadata,
        headline="List vs Tuple: Which One to Choose?",
        subheadline="Mutability, Performance aur Memory ka Asal Farq",
        code_snippet=(
            "a = [1, 2]\n"
            "a.append(3)\n"
            "b = (1, 2)\n"
            "# b.append(3) -> AttributeError!\n"
            "print('List:', a, '| Tuple:', b)"
        ),
        code_output="List: [1, 2, 3] | Tuple: (1, 2)",
        teaching_points=[
            "Mutability: List [ ] dynamic hoti hai aur runtime pe modify ho sakti hai.",
            "Immutability: Tuple ( ) freeze hoti hai, values safe aur locked rehti hain.",
            "Performance: Tuples memory kam leti hain aur lookup mein fast hoti hain.",
        ],
        practice_question=PracticeQuestion(
            question="Which data structure throws AttributeError when appending?",
            options=["A) list", "B) tuple", "C) set", "D) dict"],
            answer="B) tuple",
            explanation="Tuples are immutable; once created, items cannot be added.",
        ),
        cta="Save for Practice & Share with Peers",
        visual_concept="List vs Tuple code comparison with append and immutability",
        captions=CaptionPack(
            instagram="Python developers: Stop guessing between Lists and Tuples. Save this guide!",
            facebook="Learn the memory and performance difference between Python Lists and Tuples.",
            tiktok="Python Lists vs Tuples explained in 30 seconds!",
        ),
        hashtags=HashtagPack(
            instagram=["#PythonTips", "#CodingLife", "#TechBuilt", "#LearnPython", "#DevTips"],
            facebook=["#Python", "#Programming", "#TechEducation"],
            tiktok=["#python", "#coding", "#softwareengineer"],
        ),
        alt_text="Educational developer graphic showing Python List vs Tuple differences.",
    )


def create_sample_variable_poster() -> PosterContent:
    metadata = ContentMetadata(
        brand="TechBuilt Open School",
        content_type=ContentType.POSTER,
        language=ContentLanguage.ROMAN_URDU,
        content_pillar="Python & Architecture",
        topic="What Is a Python Variable?",
        target_audience="Beginner Python learners",
        objective="Master dynamic binding and heap allocation",
        tone="practical, clear, encouraging",
        difficulty=Difficulty.BEGINNER,
        cta_type="save",
        fact_sensitivity=FactSensitivity.LOW,
        prompt_template_name="poster_developer",
        prompt_template_version=2,
        model_name="gemini-2.5-flash",
        generation_parameters={},
        content_hash="d" * 64,
        quality_score=94,
    )
    return PosterContent(
        metadata=metadata,
        headline="Python Variables: Name vs Object",
        subheadline="Memory Reference aur Dynamic Binding Samajhein",
        code_snippet="x = [10, 20]\ny = x\ny.append(30)\nprint('x:', x, '| y:', y)",
        code_output="x: [10, 20, 30] | y: [10, 20, 30]",
        teaching_points=[
            "References: Variable value container nahi, heap memory reference hota hai.",
            "Dynamic Binding: Python objects runtime pe infer aur bind hote hain.",
            "Shared Mutability: y ko modify karne se x bhi change hota hai agar same object ho.",
        ],
        practice_question=PracticeQuestion(
            question="If y = x and y is modified, does x change too?",
            options=[
                "A) Yes (same object)",
                "B) No (makes copy)",
                "C) Throws error",
                "D) Only in Python 2",
            ],
            answer="A) Yes (same object)",
            explanation="Variables hold object references, so both names point to the same list.",
        ),
        cta="Save for Practice",
        visual_concept="Python variable assignment with type annotations",
        captions=CaptionPack(
            instagram="How Python variables actually work under the hood! Save this graphic.",
            facebook="Demystifying Python variables and memory binding.",
            tiktok="Python variables under the hood in 30 seconds!",
        ),
        hashtags=HashtagPack(
            instagram=["#Python", "#CleanCode", "#ComputerScience", "#TechBuilt"],
            facebook=["#PythonLearning", "#Programming"],
            tiktok=["#python", "#learntocode"],
        ),
        alt_text="Infographic explaining how Python variables bind to heap memory objects.",
    )


def main() -> None:
    output_dir = Path("storage/posters")
    output_dir.mkdir(parents=True, exist_ok=True)

    renderer = PosterRenderer()

    # 1. List vs Tuple Poster
    poster1 = create_sample_list_vs_tuple_poster()
    target1 = output_dir / "python_list_vs_tuple_1x1.png"
    result1 = renderer.render_to_file(poster1, target1)
    print(
        f"Rendered: {result1['local_path']} "
        f"({result1['width']}x{result1['height']}, {result1['size_bytes']} bytes)"
    )

    # 2. Variable Poster
    poster2 = create_sample_variable_poster()
    target2 = output_dir / "python_variables_1x1.png"
    result2 = renderer.render_to_file(poster2, target2)
    print(
        f"Rendered: {result2['local_path']} "
        f"({result2['width']}x{result2['height']}, {result2['size_bytes']} bytes)"
    )


if __name__ == "__main__":
    main()
