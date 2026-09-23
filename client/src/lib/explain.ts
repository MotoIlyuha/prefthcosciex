// «Объяснить строку» (build prompt, stage 5): a plain-Russian reading of one line of
// Python, built from the constructs that ЕГЭ programs actually use. Rule-based and
// offline: it runs in the browser, needs no server and never sees the answer.

interface Rule {
  test: RegExp;
  text: string | ((m: RegExpExecArray) => string);
}

const RULES: Rule[] = [
  { test: /^\s*#/, text: "Комментарий: Python его не выполняет." },
  { test: /^\s*(from\s+\S+\s+)?import\s+(.+)/, text: (m) => `Подключаем ${m[2]} из стандартной библиотеки.` },
  { test: /@(functools\.)?(lru_)?cache/, text: "Декоратор кэша: функция запоминает уже посчитанные значения — рекурсия (задание 16) перестаёт пересчитывать одно и то же." },
  { test: /^\s*def\s+(\w+)\s*\(([^)]*)\)/, text: (m) => `Объявляем функцию ${m[1]}(${m[2]}); её тело — строки ниже с отступом.` },
  { test: /^\s*return\b(.*)/, text: (m) => `Функция возвращает ${m[1]!.trim() || "None"} и сразу заканчивается.` },
  { test: /^\s*for\s+(.+?)\s+in\s+range\(([^)]*)\)/, text: (m) => rangeText(m[1]!, m[2]!) },
  { test: /^\s*for\s+(.+?)\s+in\s+product\(([^)]*)\)/, text: (m) => `Перебираем все наборы ${m[1]} из декартова произведения ${m[2]} — как вложенные циклы (задания 8, 2).` },
  { test: /^\s*for\s+(.+?)\s+in\s+open\(([^)]*)\)/, text: (m) => `Читаем файл ${m[2]} построчно; в ${m[1]} — очередная строка вместе с символом перевода строки.` },
  { test: /^\s*for\s+(.+?)\s+in\s+(.+):/, text: (m) => `Цикл: ${m[1]} по очереди принимает каждое значение из ${m[2]}.` },
  { test: /^\s*while\s+(.+):/, text: (m) => `Цикл «пока»: тело повторяется, пока истинно условие ${m[1]}.` },
  { test: /^\s*elif\s+(.+):/, text: (m) => `Иначе, если ${m[1]}, — выполняем блок ниже.` },
  { test: /^\s*if\s+(.+):/, text: (m) => `Условие: блок ниже выполняется, только если ${m[1]} истинно.` },
  { test: /^\s*else\s*:/, text: "Иначе: блок ниже выполняется, когда условия выше ложны." },
  { test: /\.replace\(([^,]+),\s*([^,)]+)\s*,\s*1\s*\)/, text: (m) => `Заменяем только ПЕРВОЕ вхождение ${m[1]} на ${m[2]} — как исполнитель Редактор (задание 12).` },
  { test: /\.replace\(([^,]+),\s*([^,)]+)\)/, text: (m) => `Внимание: заменяются ВСЕ вхождения ${m[1]} на ${m[2]}. В задании 12 нужна замена одного: .replace(${m[1]}, ${m[2]}, 1).` },
  { test: /open\(([^)]*)\)\.read(line)?\(\)/, text: (m) => `Читаем файл ${m[1]} целиком в строку.` },
  { test: /\.split\(([^)]*)\)/, text: (m) => `split делит строку на части ${m[1] ? `по разделителю ${m[1]}` : "по пробелам"}.` },
  { test: /int\(([^,()]+),\s*(\d+)\)/, text: (m) => `Переводим строку ${m[1]} из системы с основанием ${m[2]} в обычное число.` },
  { test: /bin\(([^)]*)\)\[2:\]/, text: (m) => `Двоичная запись ${m[1]} без префикса «0b».` },
  { test: /\bprint\((.*)\)/, text: (m) => `Выводим на экран: ${m[1]}.` },
  { test: /^\s*(\w+)\s*\+=\s*(.+)/, text: (m) => `Увеличиваем ${m[1]} на ${m[2]}.` },
  { test: /^\s*(\w+)\s*-=\s*(.+)/, text: (m) => `Уменьшаем ${m[1]} на ${m[2]}.` },
  { test: /^\s*([\w, ]+?)\s*=\s*(.+)/, text: (m) => `Присваиваем: ${m[1]} ← ${m[2]}.` },
];

const OPERATORS: [RegExp, string][] = [
  [/\/\//, "// — целочисленное деление (остаток отбрасывается)"],
  [/%/, "% — остаток от деления"],
  [/\*\*/, "** — возведение в степень"],
  [/\bnot\b/, "not — отрицание"],
  [/<=(?!=)/, "<= — меньше или равно (на логических значениях это импликация)"],
  [/\bmax\(/, "max — наибольшее"],
  [/\bmin\(/, "min — наименьшее"],
  [/\bsorted\(/, "sorted — отсортированная копия"],
  [/\blen\(/, "len — длина"],
  [/\bsum\(/, "sum — сумма"],
  [/\babs\(/, "abs — модуль (нужен для последней цифры отрицательных: abs(x) % 10)"],
  [/&/, "& — побитовое И"],
];

function rangeText(variable: string, args: string): string {
  const parts = args.split(",").map((p) => p.trim()).filter(Boolean);
  if (parts.length === 1) return `Цикл: ${variable} = 0, 1, …, ${parts[0]} − 1 (правая граница не входит).`;
  if (parts.length === 2) return `Цикл: ${variable} от ${parts[0]} до ${parts[1]} − 1 (правая граница не входит).`;
  return `Цикл: ${variable} от ${parts[0]} до ${parts[1]} (не включая) с шагом ${parts[2]}.`;
}

export function explainLine(line: string): string[] {
  const text = line.replace(/\s+$/, "");
  if (!text.trim()) return ["Пустая строка."];
  const out: string[] = [];
  for (const rule of RULES) {
    const m = rule.test.exec(text);
    if (m) {
      out.push(typeof rule.text === "string" ? rule.text : rule.text(m));
      break;
    }
  }
  const code = text.replace(/#.*$/, "").replace(/(["']).*?\1/g, "");
  for (const [re, note] of OPERATORS) if (re.test(code)) out.push(note);
  if (!out.length) out.push("Обычное выражение Python: вычисляется слева направо с учётом скобок.");
  return out;
}
