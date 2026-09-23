// Russian formatting helpers.
export function plural(n: number, one: string, few: string, many: string): string {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return many;
  if (last > 1 && last < 5) return few;
  if (last === 1) return one;
  return many;
}

export function coins(n: number): string {
  return `${n} 🪙`;
}

export function minutes(seconds: number): string {
  const m = Math.max(1, Math.round(seconds / 60));
  return `~${m} мин`;
}

export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${bytes} Б`;
}

export function dateShort(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

export const LEVEL_TITLE: Record<string, string> = { A: "40–64", B: "65–84", C: "85–100" };

export const REASONS: { code: string; text: string }[] = [
  { code: "no_method", text: "Не знал, как подступиться" },
  { code: "misread", text: "Неправильно понял условие" },
  { code: "code_bug", text: "Ошибка в коде" },
  { code: "careless", text: "Невнимательность / арифметика" },
  { code: "time", text: "Не хватило времени" },
  { code: "format", text: "Не понял, как записать ответ" },
  { code: "forgot", text: "Забыл формулу или факт" },
  { code: "other", text: "Другое" },
];

export const ANSWER_HINTS: Record<string, string> = {
  int: "Целое число",
  float: "Число",
  letters: "Буквы без пробелов",
  two_ints: "Два числа в одну строку через пробел — как на ЕГЭ",
  pairs_list: "Пары через запятую: «12 30, 15 22»",
  string: "Строка",
};

/** The same normalisation the server applies, to warn before sending (7.4). */
export function answerWarning(kind: string, raw: string, options: Record<string, unknown> = {}): string | null {
  const text = raw.trim();
  if (!text) return "Введите ответ";
  if (kind === "int" && !/^[-+]?\d+$/.test(text.replace(/\s/g, ""))) return "Ожидается целое число";
  if (kind === "two_ints" && text.split(/[\s,;]+/).filter(Boolean).length !== 2) return "Нужно два числа";
  if (kind === "letters") {
    // The alphabet decides: task 4 answers are code words over "01".
    const alphabet = typeof options.alphabet === "string" ? options.alphabet.toUpperCase() : "";
    const symbols = text.replace(/[\s,;]+/g, "").toUpperCase();
    if (alphabet && [...symbols].some((ch) => !alphabet.includes(ch))) return `Допустимы только символы: ${alphabet}`;
  }
  return null;
}
