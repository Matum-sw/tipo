import os


class AIFeedbackService:
    """Small adapter kept separate so the UI is not coupled to an API vendor."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def build_prompt(self, markdown_report: str) -> str:
        return (
            "You are a warm productivity coach. Review this student's daily time-boxing report. "
            "Give concise feedback in Korean: one strength, one bottleneck, and one next action.\n\n"
            f"{markdown_report}"
        )

    def generate_feedback(self, markdown_report: str) -> str:
        if not self.is_configured():
            return "OPENAI_API_KEY가 설정되면 이 리포트를 바탕으로 AI 피드백을 생성할 수 있습니다."

        # API call is intentionally isolated here. Install the official OpenAI SDK and
        # replace this placeholder with a Responses API call when network use is enabled.
        prompt = self.build_prompt(markdown_report)
        return f"AI 피드백 생성 준비 완료\n\n{prompt[:500]}"
