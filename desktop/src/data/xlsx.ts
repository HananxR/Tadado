// ─────────────────────────────────────────────────────────────────────────────
// 最小 xlsx 生成：一堆字符串单元格 → Excel / WPS 能直接打开的工作簿。
//
// 为什么自己写：全应用只有「导出」一处要它，为这一个按钮往依赖里塞 openpyxl 的
// 前端等价物（SheetJS 那类，几百 KB）不值当；而「导出一个 Excel」又是用户明确要
// 的格式。xlsx 的本质是一个 zip 包里放几段 XML，这段就是把它写出来。
//
// 刻意做得**刚好够用**：
//   · 只写一个工作表，单元格全部按 inlineStr（文本）写 —— 不用 sharedStrings，
//     少一个文件；数字也当文本，Excel 会标「以文本形式存储的数字」，但不会像
//     CSV 那样把 09-11 变成 9月11日、把 1/2 变成分数；
//   · zip 用 store（不压缩）：少一层实现，代价是文件大一点，而导出的都是几
//     KB 的文本。
// 需要合并单元格、多 sheet、列宽时再扩展，别为了「将来可能要」先堆参数。
// ─────────────────────────────────────────────────────────────────────────────

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** 小端写入。zip 的头部字段一律小端。 */
function put16(out: number[], value: number): void {
  out.push(value & 0xff, (value >>> 8) & 0xff);
}

function put32(out: number[], value: number): void {
  out.push(value & 0xff, (value >>> 8) & 0xff, (value >>> 16) & 0xff, (value >>> 24) & 0xff);
}

const encoder = new TextEncoder();

/** 2026-09-17 00:00 的 DOS 时间日期。固定值：包里的时间戳没有意义，写死省一次计算。 */
const DOS_TIME = 0;
const DOS_DATE = ((2026 - 1980) << 9) | (9 << 5) | 17;

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    // 控制字符（粘贴来的换行、制表符）在 XML 里非法，必须清掉，
    // 否则 Excel 会报「文件已损坏」—— 而用户只会看到导出失败
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, " ");
}

const A1 = (column: number, row: number): string => {
  let name = "";
  let rest = column + 1;
  while (rest > 0) {
    const remainder = (rest - 1) % 26;
    name = String.fromCharCode(65 + remainder) + name;
    rest = Math.floor((rest - 1) / 26);
  }
  return `${name}${row}`;
};

function sheetXml(rows: readonly (readonly string[])[]): string {
  const body = rows
    .map((row, rowIndex) => {
      const cells = row
        .map((cell, column) => {
          const ref = A1(column, rowIndex + 1);
          return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${escapeXml(cell)}</t></is></c>`;
        })
        .join("");
      // 整行空就别写 <row>：Excel 能开，但没有意义，只会让文件变大
      return row.length > 0 ? `<row r="${rowIndex + 1}">${cells}</row>` : "";
    })
    .join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>${body}</sheetData></worksheet>`;
}

const FILES = (sheet: string): { name: string; text: string }[] => [
  {
    name: "[Content_Types].xml",
    text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>`,
  },
  {
    name: "_rels/.rels",
    text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
  },
  {
    name: "xl/workbook.xml",
    text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>`,
  },
  {
    name: "xl/_rels/workbook.xml.rels",
    text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`,
  },
  { name: "xl/worksheets/sheet1.xml", text: sheet },
];

/**
 * 一段二维字符串 → xlsx 文件的字节。
 *
 * 第一行就是表头，调用方自己保证（导出的表都带表头，没有表头的 xlsx 打开是
 * 一片没有名字的格子）。
 */
export function toXlsx(rows: readonly (readonly string[])[]): ArrayBuffer {
  const out: number[] = [];
  const central: number[] = [];
  let entries = 0;

  for (const file of FILES(sheetXml(rows))) {
    const name = encoder.encode(file.name);
    const data = encoder.encode(file.text);
    const crc = crc32(data);
    const offset = out.length;

    out.push(0x50, 0x4b, 0x03, 0x04); // local file header
    put16(out, 20); // version needed
    put16(out, 0); // flags
    put16(out, 0); // method: store
    put16(out, DOS_TIME);
    put16(out, DOS_DATE);
    put32(out, crc);
    put32(out, data.length);
    put32(out, data.length);
    put16(out, name.length);
    put16(out, 0); // extra
    for (const byte of name) out.push(byte);
    for (const byte of data) out.push(byte);

    central.push(0x50, 0x4b, 0x01, 0x02);
    put16(central, 20); // version made by
    put16(central, 20); // version needed
    put16(central, 0);
    put16(central, 0);
    put16(central, DOS_TIME);
    put16(central, DOS_DATE);
    put32(central, crc);
    put32(central, data.length);
    put32(central, data.length);
    put16(central, name.length);
    put16(central, 0); // extra
    put16(central, 0); // comment
    put16(central, 0); // disk
    put16(central, 0); // internal attrs
    put32(central, 0); // external attrs
    put32(central, offset);
    for (const byte of name) central.push(byte);

    entries += 1;
  }

  const directoryAt = out.length;
  out.push(...central);

  out.push(0x50, 0x4b, 0x05, 0x06); // end of central directory
  put16(out, 0); // disk number
  put16(out, 0); // disk with directory
  put16(out, entries);
  put16(out, entries);
  put32(out, central.length);
  put32(out, directoryAt);
  put16(out, 0); // comment

  const buffer = new ArrayBuffer(out.length);
  new Uint8Array(buffer).set(out);
  // 交 ArrayBuffer 而不是 Uint8Array：视图类型带 ArrayBufferLike 泛型，
  // 往下传给 Blob 时还要断言一次，而这里本来就是一整块独占的缓冲
  return buffer;
}
