import os
import json
import re


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
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "") or os.getenv("HUGGINGFACE_API_KEY", "")

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def provider(self) -> str:
        if self.api_key.startswith("sk-"):
            return "openai"
        if self.api_key.startswith("hf_") or self.api_key.startswith("hf-"):
            return "huggingface"
        return "unknown"

    def build_prompt(self, markdown_report: str) -> str:
        return (
            "You are a warm productivity coach. Review this student's daily time-boxing report. "
            "Give concise feedback in Korean: one strength, one bottleneck, and one next action.\n\n"
            f"{markdown_report}"
        )

    def generate_feedback(self, markdown_report: str) -> str:
        if not self.is_configured():
            return "API 키가 설정되면 이 리포트를 바탕으로 AI 피드백을 생성할 수 있습니다."

        prompt = self.build_prompt(markdown_report)

        if self.provider() == "openai":
            return self._openai_feedback(prompt)

        if self.provider() == "huggingface":
            return self._huggingface_feedback(prompt)

        raise ValueError("지원되지 않는 API 키 형식입니다. OpenAI는 sk-, Hugging Face는 hf_ 로 시작해야 합니다.")

    def generate_realistic_schedule(self, context: dict) -> dict:
        if not self.is_configured():
            raise ValueError("API 키가 필요합니다.")

        if self.provider() == "openai":
            return self._openai_schedule(context)

        if self.provider() == "huggingface":
            return self._huggingface_schedule(context)

        raise ValueError("지원되지 않는 API 키 형식입니다. OpenAI는 sk-, Hugging Face는 hf_ 로 시작해야 합니다.")

    def _openai_feedback(self, prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 패키지가 설치되어 있지 않습니다. requirements.txt를 설치해주세요.") from exc

        client = OpenAI(api_key=self.api_key)

        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions="Give concise Korean feedback.",
            input=prompt,
        )

        return response.output_text

    def _huggingface_feedback(self, prompt: str) -> str:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("huggingface_hub 패키지가 설치되어 있지 않습니다. pip install huggingface_hub 를 실행해주세요.") from exc

        client = InferenceClient(api_key=self.api_key)

        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=700,
        )

        return response.choices[0].message.content

    def _openai_schedule(self, context: dict) -> dict:
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

    def _huggingface_schedule(self, context: dict) -> dict:
        try:
            from huggingface_hub import InferenceClient
        except ImportError as exc:
            raise RuntimeError("huggingface_hub 패키지가 설치되어 있지 않습니다. pip install huggingface_hub 를 실행해주세요.") from exc

        client = InferenceClient(api_key=self.api_key)

        prompt = (
            "너는 현실적인 한국어 공부 일정 관리자야.\n"
            "제공된 앱 데이터만 사용해. 없는 할 일은 만들지 마.\n"
            "남은 계획이 지금부터 현실적으로 가능한지 판단해.\n"
            "모든 일이 남은 시간 안에 안 들어가면 솔직히 말하고 가능한 만큼만 배정해.\n"
            "반드시 editable_block_keys에 있는 block_key만 사용해.\n"
            "protected_block_keys에는 절대 배정하지 마.\n"
            "휴식, 여유, 회복 시간은 todo_id를 0으로 사용해.\n"
            "반드시 JSON만 출력해. JSON 밖에 설명을 쓰지 마.\n\n"
            "출력 형식:\n"
            "{\n"
            '  "summary": "요약",\n'
            '  "realistic_reason": "현실성 판단 이유",\n'
            '  "schedule": [\n'
            '    {"block_key": "블록키", "todo_id": 0, "label": "휴식", "reason": "이유"}\n'
            "  ]\n"
            "}\n\n"
            f"앱 데이터:\n{json.dumps(context, ensure_ascii=False)}"
        )

        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
        )

        text = response.choices[0].message.content.strip()
        text = self._extract_json(text)

        return json.loads(text)

    def _extract_json(self, text: str) -> str:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError(f"AI가 JSON 형식으로 답하지 않았습니다:\n{text}")
        return match.group(0)
