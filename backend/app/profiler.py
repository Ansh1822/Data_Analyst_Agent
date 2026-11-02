"""Section 1 - Data profiling. No LLM here: cheap, deterministic facts about the file."""
import json
from pathlib import Path

import pandas as pd


def load_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1")


def profile_dataframe(df: pd.DataFrame) -> dict:
    columns = []
    for name in df.columns:
        s = df[name]
        info = {
            "name": str(name),
            "dtype": str(s.dtype),
            "nulls": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
            "sample": s.dropna().astype(str).head(3).tolist(),
        }
        if pd.api.types.is_numeric_dtype(s) and not s.dropna().empty:
            info.update(
                min=float(s.min()), max=float(s.max()),
                mean=round(float(s.mean()), 3), median=float(s.median()),
            )
        elif not pd.api.types.is_numeric_dtype(s):
            info["top_values"] = {str(k): int(v) for k, v in s.value_counts().head(5).items()}
        columns.append(info)
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "column_info": columns,
        "head": json.loads(df.head(5).to_json(orient="records", date_format="iso")),
    }


def profile_to_text(profile: dict) -> str:
    """Compact text version that goes into every LLM prompt."""
    lines = [f"Rows: {profile['rows']}, Columns: {profile['columns']}", "Columns:"]
    for c in profile["column_info"]:
        extra = ""
        if "min" in c:
            extra = f" min={c['min']} max={c['max']} mean={c['mean']}"
        elif "top_values" in c:
            extra = f" top={c['top_values']}"
        lines.append(f"- {c['name']} ({c['dtype']}) nulls={c['nulls']} unique={c['unique']}{extra}")
    lines.append(f"First rows: {json.dumps(profile['head'][:3])}")
    return "\n".join(lines)
