import os
import json


REALISTIC_SCHEDULE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "realistic_reason", "schedule"],
    "properties": {
        "summary": {"type": "string"},
        "realistic_reason": {"type": "string"},
        "schedule": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["block_key", "todo_id", "label", "reason"],
                "properties": {
                    "block_key": {"type": "string"},
                    "todo_id": {"type": "integer"},
                    "label": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}


class AIFeedbackService:
    """Small adapter kept separate so the UI is not coupled to an API vendor."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key.strip()

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

    def generate_realistic_schedule(self, context: dict) -> dict:
        if not self.is_configured():
            raise ValueError("OpenAI API 키가 필요합니다.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 패키지가 설치되어 있지 않습니다. requirements.txt를 설치해주세요.") from exc

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=(
                "You are a realistic Korean study planner. "
                "Use only the provided app data. Do not invent tasks. "
                "Decide whether the remaining plan is realistically achievable from now. "
                "If all remaining tasks do not fit, say so honestly and schedule only the realistic amount. "
                "Only use editable_block_keys. Never schedule protected_block_keys. "
                "Use todo_id 0 for a block that should stay empty for rest, buffer, or recovery. "
                "Editable blocks omitted from schedule will be left empty. "
                "Return concise Korean reasons."
            ),
            input=json.dumps(context, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "realistic_schedule",
                    "strict": True,
                    "schema": REALISTIC_SCHEDULE_SCHEMA,
                }
            },
        )
        return json.loads(response.output_text)
