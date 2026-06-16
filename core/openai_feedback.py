import os
import json
import re
import ast


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
    def __init__(self, api_key: str | None = None):
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY", "")
            or os.getenv("HUGGINGFACE_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
        )

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key.strip()

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def provider(self) -> str:
        if self.api_key.startswith("sk-"):
            return "openai"
        if self.api_key.startswith("hf_") or self.api_key.startswith("hf-"):
            return "huggingface"
        if self.api_key.startswith("AIza"):
            return "gemini"
        return "unknown"

    def build_prompt(self, markdown_report: str) -> str:
        return (
            "You are a warm productivity coach. "
            "Give concise Korean feedback: one strength, one bottleneck, and one next action.\n\n"
            f"{markdown_report}"
        )

    def generate_feedback(self, markdown_report: str) -> str:
        if not self.is_configured():
            return "API 키가 설정되면 AI 피드백을 생성할 수 있습니다."

        provider = self.provider()
        prompt = self.build_prompt(markdown_report)

        if provider == "openai":
            return self._openai_feedback(prompt)
        if provider == "huggingface":
            return self._huggingface_feedback(prompt)
        if provider == "gemini":
            return self._gemini_feedback(prompt)

        raise ValueError("지원되지 않는 API 키입니다. OpenAI는 sk-, Hugging Face는 hf_, Gemini는 AIza 로 시작해야 합니다.")

    def generate_realistic_schedule(self, context: dict) -> dict:
        if not self.is_configured():
            raise ValueError("API 키가 필요합니다.")

        provider = self.provider()

        if provider == "openai":
            return self._openai_schedule(context)
        if provider == "huggingface":
            return self._huggingface_schedule(context)
        if provider == "gemini":
            return self._gemini_schedule(context)

        raise ValueError("지원되지 않는 API 키입니다. OpenAI는 sk-, Hugging Face는 hf_, Gemini는 AIza 로 시작해야 합니다.")

    def _openai_feedback(self, prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 패키지가 없습니다. pip install openai 를 실행해주세요.") from exc

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
            raise RuntimeError("huggingface_hub 패키지가 없습니다. pip install huggingface_hub 를 실행해주세요.") from exc

        client = InferenceClient(api_key=self.api_key)
        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
        )
        return response.choices[0].message.content

    def _gemini_feedback(self, prompt: str) -> str:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError("google-generativeai 패키지가 없습니다. pip install google-generativeai 를 실행해주세요.") from exc

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text

    def _openai_schedule(self, context: dict) -> dict:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai 패키지가 없습니다. pip install openai 를 실행해주세요.") from exc

        client = OpenAI(api_key=self.api_key)
        response = client.responses.create(
            model="gpt-4.1-mini",
            instructions=self._schedule_instructions_en(),
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
            raise RuntimeError("huggingface_hub 패키지가 없습니다. pip install huggingface_hub 를 실행해주세요.") from exc

        client = InferenceClient(api_key=self.api_key)
        response = client.chat.completions.create(
            model="Qwen/Qwen2.5-7B-Instruct",
            messages=[{"role": "user", "content": self._schedule_prompt_ko(context)}],
            max_tokens=3000,
        )
        return self._safe_json_loads(response.choices[0].message.content)

    def _gemini_schedule(self, context: dict) -> dict:
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise RuntimeError("google-generativeai 패키지가 없습니다. pip install google-generativeai 를 실행해주세요.") from exc

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(self._schedule_prompt_ko(context))
        return self._safe_json_loads(response.text)

    def _schedule_instructions_en(self) -> str:
        return (
            "You are a realistic Korean study planner. "
            "Use only the provided app data. Do not invent tasks. "
            "Only use editable_block_keys. Never schedule protected_block_keys or excluded_block_keys. "
            "Use todo_id 0 for rest, buffer, or recovery. "
            "Use recent_performance_summary and recent_days.performance to calibrate today's remaining plan. "
            "Use schedule_baseline for the target task count, target block count, and typical work-buffer interval. "
            "Never keep more planned blocks than max_planned_blocks_with_20_percent_buffer when that value is provided. "
            "Compare recent planned_blocks with timer focus_segment_minutes to infer how many continuous blocks the user actually sustains. "
            "Use rule_based_proposal as the starting recommendation; only override it when the app data clearly supports a better patch. "
            "The schedule array is a patch: return only blocks that should change from current_blocks. "
            "If today's remaining plan is unrealistic, include concrete blocks to clear with todo_id 0 or move to another todo_id. "
            "Consider every todo in todos, including todos with 0 planned minutes. "
            "If schedule_alerts is not empty, address those alerts with concrete changed blocks unless there is a clear reason not to. "
            "For a too_long_continuous_task alert, do not create scattered empty gaps inside the task. Keep the first upcoming task start time fixed, compact each task forward, preserve the original gap block count between different tasks, pull later tasks forward when earlier tasks are shortened, and clear only trailing excess blocks when reduction is needed. "
            "Write realistic_reason in Korean with 3 to 5 detailed sentences, starting with '지난 10일 데이터를 분석한 결과'. "
            "Mention concrete baseline numbers when available, such as completion rate, focus-vs-plan rate, average focus segment, and work-buffer pattern."
        )

    def _schedule_prompt_ko(self, context: dict) -> str:
        return (
            "너는 현실적인 한국어 공부 일정 관리자야.\n"
            "제공된 앱 데이터만 사용해. 없는 할 일은 만들지 마.\n"
            "editable_block_keys에 있는 block_key만 사용해.\n"
            "protected_block_keys에는 절대 배정하지 마.\n"
            "휴식, 여유, 회복 시간은 todo_id를 0으로 사용해.\n"
            "반드시 JSON만 출력해. JSON 밖에 설명을 쓰지 마.\n"
            "모든 문자열은 반드시 큰따옴표를 사용해.\n"
            "schedule은 최대 12개 블록만 출력해.\n\n"
            "JSON 형식:\n"
            "{\n"
            '  "summary": "요약",\n'
            '  "realistic_reason": "현실성 판단 이유",\n'
            '  "schedule": [\n'
            '    {"block_key": "02:30", "todo_id": 1, "label": "공부", "reason": "이유"}\n'
            "  ]\n"
            "}\n\n"
            f"앱 데이터:\n{json.dumps(context, ensure_ascii=False)}"
        )

    def _extract_json(self, text: str) -> str:
        text = text.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()

        start = text.find("{")
        end = text.rfind("}")

        if start == -1:
            raise ValueError("JSON 시작 기호를 찾지 못했습니다.")

        if end == -1 or end <= start:
            text = text[start:] + "\n}"

            open_brackets = text.count("[")
            close_brackets = text.count("]")
            if open_brackets > close_brackets:
                text = text.rstrip("}") + "]\n}"

            return text

        return text[start:end + 1]

    def _safe_json_loads(self, text: str) -> dict:
        try:
            json_text = self._extract_json(text)
        except Exception:
            return self._fallback_schedule()

        candidates = []

        candidates.append(json_text)

        fixed = json_text.replace("'", '"')
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*]", "]", fixed)
        candidates.append(fixed)

        for candidate in candidates:
            try:
                data = json.loads(candidate)
                return self._normalize_schedule(data)
            except Exception:
                pass

            try:
                data = ast.literal_eval(candidate)
                return self._normalize_schedule(data)
            except Exception:
                pass

        return self._fallback_schedule()

    def _normalize_schedule(self, data: dict) -> dict:
        if not isinstance(data, dict):
            return self._fallback_schedule()

        summary = str(data.get("summary", "AI가 시간표 제안을 생성했습니다."))
        realistic_reason = str(data.get("realistic_reason", "현실적인 범위에서 일부 일정만 제안했습니다."))
        schedule = data.get("schedule", [])

        if not isinstance(schedule, list):
            schedule = []

        cleaned = []
        for item in schedule:
            if not isinstance(item, dict):
                continue

            block_key = str(item.get("block_key", "")).strip()
            try:
                todo_id = int(item.get("todo_id", 0))
            except Exception:
                todo_id = 0

            label = str(item.get("label", ""))
            reason = str(item.get("reason", ""))

            if not block_key:
                continue

            cleaned.append({
                "block_key": block_key,
                "todo_id": todo_id,
                "label": label,
                "reason": reason,
            })

        return {
            "summary": summary,
            "realistic_reason": realistic_reason,
            "schedule": cleaned,
        }

    def _fallback_schedule(self) -> dict:
        return {
            "summary": "AI가 시간표 제안을 만들었지만 JSON 형식이 불안정해 자동 적용하지 않았습니다.",
            "realistic_reason": "Hugging Face 또는 Gemini 모델은 JSON 출력이 가끔 깨질 수 있습니다. OpenAI 키를 사용하면 더 안정적입니다.",
            "schedule": [],
        }
