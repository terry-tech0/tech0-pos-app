/**
 * snake_case ⇄ camelCase の変換。設計仕様書 §5.3 共通仕様。
 *
 * ブラウザ⇄BFF は camelCase（TypeScript流）、BFF⇄バックエンドは snake_case（Python流）。
 * **変換はBFFの責務**なので、この関数は BFF の Route Handlers からだけ呼ぶ。
 * 画面側のコードは camelCase しか知らなくてよい。
 */

/** snake_case のキーを camelCase にする（再帰的に。配列の中も辿る） */
export function toCamel<T = unknown>(value: unknown): T {
  return convert(value, snakeToCamel) as T;
}

/** camelCase のキーを snake_case にする（再帰的に） */
export function toSnake<T = unknown>(value: unknown): T {
  return convert(value, camelToSnake) as T;
}

function convert(value: unknown, rename: (key: string) => string): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => convert(item, rename));
  }
  // null も typeof は "object" なので先に除く。Date 等は変換せずそのまま返す
  if (value === null || typeof value !== "object" || value instanceof Date) {
    return value;
  }
  const result: Record<string, unknown> = {};
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    result[rename(key)] = convert(child, rename);
  }
  return result;
}

function snakeToCamel(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, char: string) => char.toUpperCase());
}

function camelToSnake(key: string): string {
  return key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`);
}
