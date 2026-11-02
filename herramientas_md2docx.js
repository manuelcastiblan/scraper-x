// Convierte el instructivo de Markdown a Word, maquetando tablas, bloques de
// codigo y avisos. Uso: node md2docx.js entrada.md salida.docx
const fs = require("fs");
const path = require("path");
const d = require("docx");

const [, , ORIGEN, DESTINO] = process.argv;

// ---------------------------------------------------------------- constantes
const ANCHO = 9360;              // Letter menos margenes de 1 pulgada, en DXA
const AZUL = "1F3864";
const AZUL_CLARO = "2E5496";
const GRIS_CODIGO = "F2F2F2";
const GRIS_BORDE = "C9C9C9";
const AMARILLO_AVISO = "FFF8E1";
const NARANJA = "D4A017";
const MONO = "Consolas";
const SIMBOLOS = "Segoe UI Symbol";

// ------------------------------------------------------------------- parseo
function partirBloques(texto) {
  const lineas = texto.split("\n");
  const bloques = [];
  let i = 0;

  const sangria = (linea) => linea.match(/^ */)[0].length;

  while (i < lineas.length) {
    const linea = lineas[i];
    const limpia = linea.trim();

    if (limpia === "") { i++; continue; }

    // Bloque de codigo delimitado por ```
    const cerca = linea.match(/^(\s*)```(\S*)\s*$/);
    if (cerca) {
      const margen = cerca[1].length;
      const cuerpo = [];
      i++;
      while (i < lineas.length && !/^\s*```\s*$/.test(lineas[i])) {
        cuerpo.push(lineas[i].slice(margen));
        i++;
      }
      i++; // la cerca de cierre
      bloques.push({ tipo: "codigo", lineas: cuerpo, nivel: Math.round(margen / 3) });
      continue;
    }

    // Tabla: lineas consecutivas que empiezan por |
    if (limpia.startsWith("|")) {
      const filas = [];
      const margen = sangria(linea);
      while (i < lineas.length && lineas[i].trim().startsWith("|")) {
        const celdas = lineas[i].trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
        if (!/^[\s:|-]+$/.test(lineas[i].trim().replace(/\|/g, ""))) {
          filas.push(celdas.map((c) => c.trim()));
        }
        i++;
      }
      bloques.push({ tipo: "tabla", filas, nivel: Math.round(margen / 3) });
      continue;
    }

    // Encabezado
    const enc = limpia.match(/^(#{1,4})\s+(.*)$/);
    if (enc) {
      bloques.push({ tipo: "encabezado", grado: enc[1].length, texto: enc[2] });
      i++;
      continue;
    }

    // Linea horizontal
    if (/^-{3,}$/.test(limpia)) {
      bloques.push({ tipo: "regla" });
      i++;
      continue;
    }

    // Cita (aviso): lineas consecutivas que empiezan por >
    if (limpia.startsWith(">")) {
      const parrafos = [];
      let actual = [];
      const margen = sangria(linea);
      while (i < lineas.length && lineas[i].trim().startsWith(">")) {
        const contenido = lineas[i].trim().replace(/^>\s?/, "");
        if (contenido === "") {
          if (actual.length) { parrafos.push(actual.join(" ")); actual = []; }
        } else {
          actual.push(contenido);
        }
        i++;
      }
      if (actual.length) parrafos.push(actual.join(" "));
      bloques.push({ tipo: "aviso", parrafos, nivel: Math.round(margen / 3) });
      continue;
    }

    // Elemento de lista, numerada o con guion
    const numerada = linea.match(/^(\s*)(\d+)\.\s+(.*)$/);
    const guion = linea.match(/^(\s*)[-*]\s+(.*)$/);
    if (numerada || guion) {
      const margen = numerada ? numerada[1].length : guion[1].length;
      const marca = numerada ? `${numerada[2]}.` : null;
      const trozos = [numerada ? numerada[3] : guion[2]];
      i++;
      // Lineas de continuacion: mas sangradas, sin ser otro elemento ni bloque
      while (
        i < lineas.length &&
        lineas[i].trim() !== "" &&
        sangria(lineas[i]) > margen &&
        !/^\s*(\d+\.|[-*])\s/.test(lineas[i]) &&
        !/^\s*```/.test(lineas[i]) &&
        !lineas[i].trim().startsWith("|") &&
        !lineas[i].trim().startsWith(">")
      ) {
        trozos.push(lineas[i].trim());
        i++;
      }
      bloques.push({
        tipo: "lista",
        marca,
        texto: trozos.join(" "),
        nivel: Math.round(margen / 3),
      });
      continue;
    }

    // Parrafo corriente
    const trozos = [];
    while (
      i < lineas.length &&
      lineas[i].trim() !== "" &&
      !/^\s*(#{1,4})\s/.test(lineas[i]) &&
      !/^\s*```/.test(lineas[i]) &&
      !lineas[i].trim().startsWith("|") &&
      !lineas[i].trim().startsWith(">") &&
      !/^-{3,}$/.test(lineas[i].trim()) &&
      !/^\s*(\d+\.|[-*])\s/.test(lineas[i])
    ) {
      trozos.push(lineas[i].trim());
      i++;
    }
    bloques.push({ tipo: "parrafo", texto: trozos.join(" "), nivel: Math.round(sangria(linea) / 3) });
  }

  return bloques;
}

// --------------------------------------------------------- formato en linea
const SIMBOLO_RE = /[☑→←✓•]/;

function trozosSimbolo(texto, estilo) {
  // Los simbolos van en una fuente que seguro los tiene.
  const salida = [];
  for (const parte of texto.split(/([☑→←✓•])/)) {
    if (parte === "") continue;
    salida.push(new d.TextRun({
      text: parte,
      ...estilo,
      ...(SIMBOLO_RE.test(parte) ? { font: SIMBOLOS } : {}),
    }));
  }
  return salida;
}

function inline(texto, base = {}) {
  const partes = [];
  const re = /\*\*([^*]+)\*\*|\*([^*\n]+)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|<(https?:\/\/[^>]+)>/g;
  let ultimo = 0;
  let m;
  while ((m = re.exec(texto)) !== null) {
    if (m.index > ultimo) {
      partes.push(...trozosSimbolo(texto.slice(ultimo, m.index), base));
    }
    if (m[1] !== undefined) {
      partes.push(...trozosSimbolo(m[1], { ...base, bold: true }));
    } else if (m[2] !== undefined) {
      partes.push(...trozosSimbolo(m[2], { ...base, italics: true }));
    } else if (m[3] !== undefined) {
      partes.push(new d.TextRun({
        text: m[3],
        font: MONO,
        size: base.size ? base.size - 1 : 20,
        shading: { type: d.ShadingType.CLEAR, fill: GRIS_CODIGO },
      }));
    } else if (m[4] !== undefined) {
      const destino = m[5];
      if (destino.startsWith("#")) {
        // Enlace interno del indice: en Word queda como texto.
        partes.push(...trozosSimbolo(m[4], base));
      } else {
        partes.push(new d.ExternalHyperlink({
          link: destino,
          children: [new d.TextRun({ text: m[4], ...base, style: "Hyperlink" })],
        }));
      }
    } else if (m[6] !== undefined) {
      partes.push(new d.ExternalHyperlink({
        link: m[6],
        children: [new d.TextRun({ text: m[6], ...base, style: "Hyperlink" })],
      }));
    }
    ultimo = re.lastIndex;
  }
  if (ultimo < texto.length) partes.push(...trozosSimbolo(texto.slice(ultimo), base));
  return partes.length ? partes : [new d.TextRun({ text: "", ...base })];
}

// ------------------------------------------------------------- construccion
function anchosColumna(columnas) {
  if (columnas === 2) return [3100, 6260];
  if (columnas === 3) return [2500, 3100, 3760];
  if (columnas === 4) return [2340, 2340, 2340, 2340];
  const parte = Math.floor(ANCHO / columnas);
  return Array(columnas).fill(parte);
}

function celda(texto, anchura, cabecera) {
  return new d.TableCell({
    width: { size: anchura, type: d.WidthType.DXA },
    shading: cabecera ? { type: d.ShadingType.CLEAR, fill: AZUL, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [
      new d.Paragraph({
        spacing: { before: 0, after: 0, line: 252 },
        children: inline(texto, cabecera ? { bold: true, color: "FFFFFF", size: 19 } : { size: 19 }),
      }),
    ],
  });
}

function tabla(filas) {
  const columnas = Math.max(...filas.map((f) => f.length));
  const anchos = anchosColumna(columnas);
  const borde = { style: d.BorderStyle.SINGLE, size: 4, color: GRIS_BORDE };
  return new d.Table({
    columnWidths: anchos,
    width: { size: ANCHO, type: d.WidthType.DXA },
    borders: { top: borde, bottom: borde, left: borde, right: borde,
               insideHorizontal: borde, insideVertical: borde },
    rows: filas.map((fila, n) => new d.TableRow({
      tableHeader: n === 0,
      children: anchos.map((ancho, c) => celda(fila[c] ?? "", ancho, n === 0)),
    })),
  });
}

function bloqueCodigo(lineas, nivel) {
  const borde = { style: d.BorderStyle.SINGLE, size: 4, color: GRIS_BORDE };
  return lineas.map((texto, n) => new d.Paragraph({
    shading: { type: d.ShadingType.CLEAR, fill: GRIS_CODIGO },
    spacing: { before: n === 0 ? 120 : 0, after: n === lineas.length - 1 ? 160 : 0, line: 240 },
    indent: { left: 180 + nivel * 300, right: 180 },
    border: {
      left: borde,
      right: borde,
      top: n === 0 ? borde : undefined,
      bottom: n === lineas.length - 1 ? borde : undefined,
    },
    keepLines: true,
    keepNext: n < lineas.length - 1,
    children: [new d.TextRun({ text: texto === "" ? " " : texto, font: MONO, size: 18 })],
  }));
}

function aviso(parrafos, nivel) {
  const barra = { style: d.BorderStyle.SINGLE, size: 18, color: NARANJA };
  const fino = { style: d.BorderStyle.SINGLE, size: 2, color: AMARILLO_AVISO };
  return parrafos.map((texto, n) => new d.Paragraph({
    shading: { type: d.ShadingType.CLEAR, fill: AMARILLO_AVISO },
    spacing: { before: n === 0 ? 160 : 0, after: n === parrafos.length - 1 ? 200 : 100, line: 264 },
    indent: { left: 240 + nivel * 300, right: 120 },
    border: {
      left: barra,
      right: fino,
      top: n === 0 ? fino : undefined,
      bottom: n === parrafos.length - 1 ? fino : undefined,
    },
    children: inline(texto),
  }));
}

function construir(bloques) {
  const hijos = [];
  let primerEncabezado = true;

  for (const b of bloques) {
    switch (b.tipo) {
      case "encabezado": {
        if (b.grado === 1) {
          hijos.push(new d.Paragraph({
            heading: d.HeadingLevel.HEADING_1,
            children: inline(b.texto),
          }));
          primerEncabezado = false;
        } else {
          hijos.push(new d.Paragraph({
            heading: b.grado === 2 ? d.HeadingLevel.HEADING_2 : d.HeadingLevel.HEADING_3,
            pageBreakBefore: false,
            children: inline(b.texto),
          }));
        }
        break;
      }
      case "parrafo":
        hijos.push(new d.Paragraph({
          indent: b.nivel ? { left: b.nivel * 300 } : undefined,
          children: inline(b.texto),
        }));
        break;
      case "lista":
        hijos.push(new d.Paragraph({
          indent: { left: 360 + b.nivel * 300, hanging: 300 },
          spacing: { before: 40, after: 80, line: 264 },
          children: [
            new d.TextRun({ text: b.marca ? `${b.marca}\t` : "• ", bold: !!b.marca,
                            font: b.marca ? undefined : SIMBOLOS }),
            ...inline(b.texto),
          ],
          tabStops: b.marca ? [{ type: d.TabStopType.LEFT, position: 360 + b.nivel * 300 }] : undefined,
        }));
        break;
      case "codigo":
        hijos.push(...bloqueCodigo(b.lineas, b.nivel));
        break;
      case "tabla":
        hijos.push(tabla(b.filas));
        hijos.push(new d.Paragraph({ spacing: { before: 0, after: 160 }, children: [] }));
        break;
      case "aviso":
        hijos.push(...aviso(b.parrafos, b.nivel));
        break;
      case "regla":
        // Los encabezados ya separan visualmente; la regla sobra en Word.
        break;
    }
  }
  return hijos;
}

// ------------------------------------------------------------------ salida
const marcado = fs.readFileSync(ORIGEN, "utf8");
const bloques = partirBloques(marcado);

const documento = new d.Document({
  creator: "scraper-x",
  title: "Instalación en Windows, desde cero",
  description: "Guía de instalación de scraper-x en Windows",
  styles: {
    default: {
      document: {
        run: { font: "Calibri", size: 21 },
        paragraph: { spacing: { before: 0, after: 140, line: 276 } },
      },
      hyperlink: { run: { color: "0563C1", underline: {} } },
    },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 40, bold: true, color: AZUL, font: "Calibri" },
        paragraph: { spacing: { before: 0, after: 240 } },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 27, bold: true, color: AZUL_CLARO, font: "Calibri" },
        paragraph: {
          spacing: { before: 360, after: 160 },
          border: { bottom: { style: d.BorderStyle.SINGLE, size: 6, color: "D9D9D9", space: 4 } },
          keepNext: true,
        },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 23, bold: true, color: AZUL_CLARO, font: "Calibri" },
        paragraph: { spacing: { before: 260, after: 120 }, keepNext: true },
      },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },   // Carta
        margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 },
      },
    },
    footers: {
      default: new d.Footer({
        children: [new d.Paragraph({
          alignment: d.AlignmentType.CENTER,
          spacing: { before: 120, after: 0 },
          children: [
            new d.TextRun({ text: "scraper-x · instalación en Windows · página ", size: 17, color: "808080" }),
            new d.TextRun({ children: [d.PageNumber.CURRENT], size: 17, color: "808080" }),
            new d.TextRun({ text: " de ", size: 17, color: "808080" }),
            new d.TextRun({ children: [d.PageNumber.TOTAL_PAGES], size: 17, color: "808080" }),
          ],
        })],
      }),
    },
    children: construir(bloques),
  }],
});

d.Packer.toBuffer(documento).then((buffer) => {
  fs.writeFileSync(DESTINO, buffer);
  const bloquesPorTipo = bloques.reduce((acc, b) => {
    acc[b.tipo] = (acc[b.tipo] || 0) + 1;
    return acc;
  }, {});
  console.log("escrito:", DESTINO, (buffer.length / 1024).toFixed(0) + " KB");
  console.log("bloques:", JSON.stringify(bloquesPorTipo));
});
