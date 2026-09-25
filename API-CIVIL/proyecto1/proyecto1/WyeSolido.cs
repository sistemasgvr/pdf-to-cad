using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;

namespace Civil3DBasico
{
    // ─────────────────────────────────────────────────────────────────────────
    //  ACCESORIOS DE PRESIÓN COMO SÓLIDO 3D (alternativa al catálogo)
    // ─────────────────────────────────────────────────────────────────────────
    //  Sirve para Y (Wye), Tee y Codo (Elbow). Motivo: el catálogo trae solo
    //  unos pocos ángulos fijos (Y de 30/45/60/75/90°, codos de 11.25/22.5/
    //  45/90°…) y cubrir cada combinación de ángulo × diámetro exigiría crear
    //  cientos de familias. Aquí la pieza se GENERA con la geometría exacta de
    //  la juntura: un brazo por tubo que llega, al ángulo real, con el diámetro
    //  real de ese tubo (así una Y reductora sale bien sin pieza especial).
    //
    //  Forma de cada brazo (igual que un tubo push-on de fundición):
    //
    //      centro                                    extremo del brazo
    //        │                                              │
    //        ├──────── cuerpo Ø = tubo ─────────┬─ campana ─┤
    //        │                                  └───────────┤ ← embocadura:
    //        │                                                 el tubo entra
    //
    //  El cuerpo tiene el MISMO diámetro exterior que la tubería 3D de Civil
    //  3D, así que empalma sin escalón. La campana del extremo es un
    //  ensanchamiento que envuelve la punta del tubo (encaje macho-hembra).
    //
    //  Todos los brazos se unen con BooleanOperation.BoolUnite en un único
    //  Solid3d, así que la pieza se selecciona y se mueve como una sola cosa.
    //
    //  Rigidez en Z (pedido del usuario): la pieza es un cuerpo RÍGIDO. Si los
    //  tubos que llegan traen cotas distintas, los brazos NO se doblan para
    //  seguirlos: todos salen horizontales desde una Z común y son los tubos
    //  los que se recortan contra la pieza. Ver `Aplanar`.
    // ─────────────────────────────────────────────────────────────────────────
    internal static class WyeSolido
    {
        internal const string CAPA = "PDFCAD_WYE_SOLIDO";
        internal const string APP_XDATA = "PDFCAD_FITTING";

        // Largo del cuerpo de cada brazo de una Y, en múltiplos del diámetro:
        // necesita tramo común antes de que el ramal abra.
        private const double LARGO_BRAZO_D = 1.25;
        // Una Tee es más compacta: los brazos salen casi a ras del cuerpo.
        private const double LARGO_BRAZO_TEE_D = 0.75;
        // Largo de la campana (embocadura) en múltiplos del diámetro.
        private const double LARGO_CAMPANA_D = 0.45;
        // Holgura radial entre el exterior del tubo y el interior de la
        // campana, en pies. Es el juego real de un empalme push-on.
        private const double HOLGURA_FT = 0.02;
        // Espesor de pared de la campana, en pies.
        private const double PARED_FT = 0.04;
        // Cuánto monta la campana SOBRE el cuerpo, en múltiplos del diámetro.
        // Sin solape, los dos sólidos solo se tocan en un plano y la unión deja
        // un escalón visible; con él, la campana envuelve el final del cuerpo.
        private const double MONTAJE_CAMPANA_D = 0.10;
        // Cuánto entra la punta del tubo dentro de la campana, como fracción
        // del largo de la campana. 1.0 = hasta el fondo; 0.75 deja el juego de
        // montaje que tienen los empalmes reales.
        private const double CALADO_EN_CAMPANA = 0.75;
        // Cuánto MENOS se recorta el tubo, en pies: lo mete un poco más dentro
        // de la campana para que el empalme se vea cerrado en planta (con el
        // calado solo, quedaba una ranura visible entre tubo y accesorio).
        private const double SOLAPE_EXTRA_FT = 0.12;
        // Radio de curvatura del eje de un codo, en múltiplos del diámetro.
        // 1.0·D = codo de radio corto (el estándar en fundición dúctil). Subirlo
        // alarga la pieza rápido en giros cerrados, porque la tangencia va como
        // R/tan(θ/2).
        private const double RADIO_CURVA_D = 1.0;
        // Collar recto entre el fin de la curva y la campana, en múltiplos del
        // diámetro. Solo es el labio para que la campana apoye.
        private const double COLLAR_CODO_D = 0.12;
        // Tope de la distancia vértice→tangencia, en múltiplos del diámetro.
        // Evita que un codo de giro cerrado se estire (ver ConstruirCodo).
        private const double TANGENCIA_MAX_D = 0.85;
        // Radio de curvatura MÍNIMO del eje, en múltiplos del diámetro. Por
        // debajo de ~1·D el tubo se dobla sobre sí mismo: el barrido se
        // auto-intersecta y AutoCAD falla con eGeneralModelingFailure. Este
        // piso manda sobre TANGENCIA_MAX_D — antes que deformar la pieza,
        // se acepta que quede más larga y se recortan los tubos contra ella.
        private const double RADIO_CURVA_MIN_D = 1.0;
        // A partir de esta deflexión el codo se considera CERRADO (codo de
        // retorno): se curva con el radio mínimo viable en vez del de 1·D, para
        // recortar la menor cantidad de tubería posible. Por debajo, los codos
        // conservan su radio normal.
        private const double GIRO_CERRADO_DEG = 135.0;
        // Por debajo de este ángulo entre ejes los dos tubos van prácticamente
        // superpuestos: la tangencia se iría al infinito, no hay curva posible.
        private const double ANG_EJES_MIN_DEG = 2.0;

        // Radio de eje más cerrado que admite un codo sin fallar: las dos
        // campanas, a cada lado de la curva, quedan separadas por 2R, y tienen
        // que caber enteras más la holgura mínima:
        //     2R ≥ 2·(D/2 + HOLGURA + PARED) + SEPARACION_MIN
        // Como la campana es más ancha que el tubo, esto también garantiza que
        // el cuerpo no se superpone consigo mismo (R − D/2 > 0).
        private static double RadioMinimoViable(double d) =>
            d / 2.0 + HOLGURA_FT + PARED_FT + SEPARACION_MIN_FT / 2.0;
        // Holgura mínima entre las paredes de dos brazos contiguos, en pies.
        // Si el ángulo entre ellos es tan cerrado que sus cuerpos se tocarían,
        // se alargan los dos lo justo para separarlos (ver `SepararBrazos`).
        private const double SEPARACION_MIN_FT = 0.10;
        // A partir de esta inclinación (grados sobre el plano) un brazo se trata
        // como salida VERTICAL y conserva su dirección aunque la pieza sea
        // rígida en Z. Ver `EsRamalVertical`.
        private const double PENDIENTE_VERTICAL_DEG = 60.0;
        // El tronco de una Y lleva un cuerpo un poco más grueso que el tubo,
        // como una pieza fundida. Con tronco y ramal del MISMO diámetro y ejes
        // que se cortan en el centro, la costura del ramal bajaba hasta el eje
        // del tronco y la Y se veía hundida (muy visible a 20°). Con el ramal
        // más delgado que el cuerpo, el ramal SALE del cuerpo y la costura queda
        // arriba. 0.03 ft es la mitad de la campana (HOLGURA + PARED = 0.06):
        // las campanas del tronco se siguen distinguiendo.
        internal const double ENGROSE_TRONCO_Y_FT = 0.03;

        internal class Brazo
        {
            internal Vector3d Direccion;       // desde el centro hacia el tubo (unitario)
            internal double DiamFt;            // diámetro EXTERIOR del tubo, en pies
            internal double LargoCuerpoFt;     // se ajusta en SepararBrazos
            internal ObjectId PipeId;          // tubo a recortar (puede ser Null)
            internal int Port;                 // 0 = StartPoint en la juntura, 1 = EndPoint
            // Radio extra del CUERPO de este brazo (no de su campana). Solo lo
            // llevan los dos brazos del tronco de una Y: ver ENGROSE_TRONCO_Y_FT.
            internal double EngroseFt;

            // Distancia desde el centro hasta donde debe MORIR el tubo: la
            // punta entra en la campana pero no llega al fondo. Se le resta el
            // solape extra para que el empalme se vea bien cerrado en planta.
            internal double AlcanceTuboFt =>
                LargoCuerpoFt + DiamFt * LARGO_CAMPANA_D * CALADO_EN_CAMPANA
                - SOLAPE_EXTRA_FT;

            // Distancia desde el centro hasta la BOCA del brazo (borde exterior
            // de la campana): es el «puerto» visible de la pieza.
            internal double BocaFt => LargoCuerpoFt + DiamFt * LARGO_CAMPANA_D;

            internal Brazo Copia() => new Brazo
            {
                Direccion = Direccion, DiamFt = DiamFt, PipeId = PipeId, Port = Port,
            };
        }

        // Registro de las piezas creadas en este IMPORTAR_RED. Las conexiones
        // verticales (CROSS) se procesan DESPUÉS de armar las redes; cuando una
        // tiene que reemplazar una pieza ya colocada (el codo de un vértice que
        // pasa a ser Wye) la busca aquí, con los tubos que esa pieza sujetaba.
        internal class Registro
        {
            internal ObjectId SolidId;
            internal string Tipo;
            internal Point3d Centro;
            internal List<Brazo> Brazos;
        }
        internal static readonly List<Registro> Creadas = new List<Registro>();

        // Pieza del tipo pedido cuyo centro cae a ≤tolXY en planta y ≤tolZ en
        // cota del punto dado, o null.
        internal static Registro BuscarCreada(string tipo, Point3d p, double tolXY, double tolZ)
        {
            Registro mejor = null; double mejorD = double.MaxValue;
            foreach (var r in Creadas)
            {
                if (r.Tipo != tipo) continue;
                double dxy = Math.Sqrt((r.Centro.X - p.X) * (r.Centro.X - p.X) +
                                       (r.Centro.Y - p.Y) * (r.Centro.Y - p.Y));
                if (dxy > tolXY || Math.Abs(r.Centro.Z - p.Z) > tolZ) continue;
                if (dxy < mejorD) { mejorD = dxy; mejor = r; }
            }
            return mejor;
        }

        // Datos descriptivos que se graban como XDATA en la pieza, para que el
        // ingeniero civil pueda consultarlos/filtrarlos en el dibujo.
        internal class Info
        {
            internal string Tipo = "";            // WYE | TEE | ELBOW
            internal double AnguloDeg;            // ángulo característico de la pieza
            internal double DiamPrincipalIn;      // Ø del tubo mayor (tronco)
            internal double DiamRamalIn;          // Ø del ramal (= principal si no hay)
            internal string Material = "";
            internal string Red = "";             // nombre de la red
        }

        // Construye la pieza, la deja en el modelspace, le graba el XDATA y
        // RECORTA los tubos para que no se metan hasta el fondo del sólido.
        // Devuelve el ObjectId del Solid3d, o ObjectId.Null si no se pudo.
        internal static ObjectId Crear(
            Database db, Transaction tr, Point3d centro,
            List<Brazo> brazos, Info info, Editor ed)
        {
            if (brazos == null || brazos.Count < 2) return ObjectId.Null;

            string tipo = info?.Tipo ?? "";
            // Eje Z rígido: la pieza vive en un solo plano horizontal.
            Point3d centroPlano = Aplanar(centro, brazos, tipo);
            // Solo la Y puede tener dos salidas tan juntas que sus campanas se
            // choquen (es el caso de la imagen 3 del usuario). En una Tee los
            // brazos van a 90°/180° y en un codo solo hay dos: ahí alargar no
            // arregla nada y solo estira la pieza.
            if (tipo == "WYE") MarcarTroncoY(brazos);
            // Una pieza nunca puede chocar consigo misma: ninguna campana dentro
            // del cuerpo de otro brazo, y ninguna campana contra otra. Ambas
            // reglas solo alargan cuando hay choque real (una Tee a 90° o una Y
            // abierta quedan igual); a 72° la Tee chocaba y salía montada.
            if (tipo == "WYE" || tipo == "TEE" || tipo == "CROSS")
            {
                SacarCampanasDelCuerpo(brazos, ed);
                SepararBrazos(brazos, ed);
            }

            Solid3d pieza = null;
            try
            {
                // Un codo (2 brazos) NO son dos cilindros pegados: eso deja un
                // pico sin la curva, que es justo lo característico de la pieza.
                // Se construye barriendo la sección por una trayectoria con arco.
                if (brazos.Count == 2)
                    pieza = ConstruirCodo(centroPlano, brazos[0], brazos[1], ed);

                if (pieza == null)
                {
                    foreach (var b in brazos)
                    {
                        var brazoSolido = ConstruirBrazo(centroPlano, b);
                        if (brazoSolido == null) continue;
                        if (pieza == null) { pieza = brazoSolido; continue; }
                        try
                        {
                            pieza.BooleanOperation(BooleanOperationType.BoolUnite, brazoSolido);
                            // BoolUnite consume el operando; no hay que desecharlo.
                        }
                        catch
                        {
                            // Si la unión falla, el operando queda huérfano: soltarlo.
                            try { brazoSolido.Dispose(); } catch { }
                        }
                    }
                }
                if (pieza == null) return ObjectId.Null;

                AsegurarCapa(db, tr);
                pieza.Layer = CAPA;
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                ObjectId id = ms.AppendEntity(pieza);
                tr.AddNewlyCreatedDBObject(pieza, true);

                GrabarXData(db, tr, pieza, info, brazos, centroPlano, ed);
                // Property Set visible en la paleta Propiedades (el XDATA no se ve).
                AccesorioPropertySet.AplicarDesdeXData(db, tr, pieza, ed);
                RecortarTubos(tr, centroPlano, brazos, ed);
                Creadas.Add(new Registro
                {
                    SolidId = id, Tipo = info?.Tipo ?? "", Centro = centroPlano,
                    Brazos = brazos.Select(b => b.Copia()).ToList(),
                });
                return id;
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n  ⚠ [FITTING-SOLIDO] No se pudo construir la pieza: {ex.Message}");
                try { pieza?.Dispose(); } catch { }
                return ObjectId.Null;
            }
        }

        // ── Eje Z rígido (SOLO Tee y Wye) ───────────────────────────────────
        // Una Tee o una Y es un cuerpo rígido de fábrica: no se dobla para
        // seguir tubos que llegan con pendientes distintas, así que sus brazos
        // se enderezan a HORIZONTAL. El desnivel lo absorbe la holgura de la
        // campana, como en obra.
        //
        // EXCEPCIÓN: un ramal que sale de verdad en VERTICAL (una bajante que
        // nace de una tubería horizontal, o una subida a un hidrante) es una
        // salida legítima de la pieza, no un tubo con pendiente. Ese brazo
        // conserva su dirección: la Tee sale orientada hacia abajo (o arriba),
        // que es justo lo que la pieza real hace. Aplanarlo lo dejaría
        // horizontal —y antes, además, el vector se anulaba: (0,0,±1) proyectado
        // a XY da el vector nulo y la dirección quedaba indefinida.
        //
        // El CODO no se aplana nunca: su razón de ser es acomodar un cambio de
        // dirección, y ese cambio puede incluir pendiente.
        private static Point3d Aplanar(Point3d centro, List<Brazo> brazos, string tipo)
        {
            // Largo base del brazo según la pieza. Una Tee es compacta (los
            // brazos salen casi a ras del cuerpo); una Y necesita algo más de
            // tramo común antes de abrir el ramal. Antes ambas usaban 1.25·D y
            // las Tee salían estiradas.
            // La cruz es compacta como una Tee (brazos casi a ras del cuerpo).
            double factor = (tipo == "TEE" || tipo == "CROSS") ? LARGO_BRAZO_TEE_D : LARGO_BRAZO_D;
            bool rigidoEnZ = (tipo == "TEE" || tipo == "WYE" || tipo == "CROSS");
            foreach (var b in brazos)
            {
                if (rigidoEnZ && !EsRamalVertical(b.Direccion))
                {
                    var d = new Vector3d(b.Direccion.X, b.Direccion.Y, 0);
                    b.Direccion = d.Length > 1e-9 ? d.GetNormal() : b.Direccion.GetNormal();
                }
                else
                {
                    // Codo: mantiene la pendiente real de los tubos.
                    b.Direccion = b.Direccion.Length > 1e-9
                        ? b.Direccion.GetNormal() : Vector3d.XAxis;
                }
                if (b.LargoCuerpoFt <= 1e-9) b.LargoCuerpoFt = b.DiamFt * factor;
            }
            return centro;
        }

        // ¿Este brazo es una salida VERTICAL de verdad (una bajante/subida), o
        // solo un tubo horizontal con algo de pendiente? Se mide la inclinación
        // contra el plano: por encima de PENDIENTE_VERTICAL_DEG se considera
        // vertical y el brazo conserva su dirección. Una tubería de obra rara
        // vez pasa del 10-15 % (≈8°), así que 60° deja un margen amplio y no
        // confunde un tubo empinado con una bajante.
        private static bool EsRamalVertical(Vector3d dir)
        {
            double h = Math.Sqrt(dir.X * dir.X + dir.Y * dir.Y);
            double v = Math.Abs(dir.Z);
            if (v < 1e-9) return false;
            if (h < 1e-9) return true;                       // vertical puro
            double incl = Math.Atan2(v, h) * 180.0 / Math.PI;
            return incl >= PENDIENTE_VERTICAL_DEG;
        }

        // Tronco de una Y = el par de brazos más recto (el más cercano a 180°);
        // esos dos llevan el cuerpo engrosado. Si quien llama ya marcó el
        // tronco (la Y de una conexión vertical, donde el tronco es la utilidad
        // que pasa), se respeta.
        private static void MarcarTroncoY(List<Brazo> brazos)
        {
            if (brazos.Count < 2 || brazos.Any(b => b.EngroseFt > 0)) return;
            Brazo a = null, b2 = null; double mejor = -1;
            for (int i = 0; i < brazos.Count; i++)
                for (int k = i + 1; k < brazos.Count; k++)
                {
                    double ang = brazos[i].Direccion.GetAngleTo(brazos[k].Direccion);
                    if (ang > mejor) { mejor = ang; a = brazos[i]; b2 = brazos[k]; }
                }
            a.EngroseFt = ENGROSE_TRONCO_Y_FT;
            b2.EngroseFt = ENGROSE_TRONCO_Y_FT;
        }

        // ── Ramal más delgado que el tronco (Y / Tee reductora) ─────────────
        // Todos los brazos nacen en el centro. Si un ramal es más DELGADO que
        // otro brazo, con su largo normal queda casi entero dentro del cuerpo
        // grueso y su campana sale medio enterrada ("entrecortada"). Se alarga
        // el ramal hasta que su campana quede ENTERA fuera de ese cuerpo; como
        // el recorte del tubo sigue al largo del brazo, el tubo delgado se
        // recorta en la misma medida.
        //
        // A una distancia s del centro sobre el eje del ramal, el borde de su
        // campana más cercano al eje del brazo grueso está a
        //     s·sin θ − r_campana·cos θ
        // de ese eje (θ = ángulo entre ejes). Queda fuera del cuerpo (radio R)
        // cuando eso ≥ R + margen, o sea  s ≥ (R + margen + r_campana·cos θ) / sin θ.
        // Se mira contra TODOS los demás brazos a ≤90° (un brazo que apunta al
        // otro lado no llega). Antes solo contra los más gruesos, y una Tee de
        // un solo diámetro con el ramal a 72° quedaba con la campana del ramal
        // metida en el brazo vecino.
        private static void SacarCampanasDelCuerpo(List<Brazo> brazos, Editor ed)
        {
            double margen = SEPARACION_MIN_FT / 2.0;
            foreach (var i in brazos)
            {
                double rCamp = i.DiamFt / 2.0 + HOLGURA_FT + PARED_FT;
                double monta = i.DiamFt * MONTAJE_CAMPANA_D;   // la campana arranca un poco antes
                double requerido = 0; Brazo grueso = null;
                foreach (var j in brazos)
                {
                    if (ReferenceEquals(i, j)) continue;
                    double th = i.Direccion.GetAngleTo(j.Direccion);
                    if (th > Math.PI / 2.0 + 1e-9) continue;
                    double sin = Math.Sin(th);
                    if (sin < Math.Sin(5.0 * Math.PI / 180.0)) continue;   // casi paralelos
                    // Se mide contra lo MÁS ANCHO del brazo vecino: su campana
                    // (más ancha que el cuerpo, incluso engrosado). Midiendo solo
                    // contra el cuerpo, en una Tee a 72° el borde de arranque de
                    // las dos campanas seguía montándose 0.01 ft.
                    double rVecino = Math.Max(j.DiamFt / 2.0 + j.EngroseFt,
                                              j.DiamFt / 2.0 + HOLGURA_FT + PARED_FT);
                    double s0 = (rVecino + margen + rCamp * Math.Cos(th)) / sin;
                    if (s0 + monta > requerido) { requerido = s0 + monta; grueso = j; }
                }
                if (grueso == null || requerido <= i.LargoCuerpoFt + 1e-6) continue;
                ed?.WriteMessage($"\n    [FITTING-SOLIDO] Brazo Ø{i.DiamFt * 12.0:F0}\" alargado " +
                    $"{i.LargoCuerpoFt:F2} → {requerido:F2} ft para que su campana quede fuera del " +
                    $"cuerpo Ø{grueso.DiamFt * 12.0:F0}\" (a {i.Direccion.GetAngleTo(grueso.Direccion) * 180.0 / Math.PI:F0}°).");
                i.LargoCuerpoFt = requerido;
            }
        }

        // ── Brazos cuyas campanas se chocan ─────────────────────────────────
        // Los CUERPOS siempre se cruzan cerca del centro: eso es correcto, es
        // la masa común de la pieza, y la unión booleana la resuelve. Lo que NO
        // puede solaparse son las CAMPANAS (el ensanchamiento del extremo): si
        // se tocan, el tubo de un brazo choca contra la boca del otro — es lo
        // que se veía en la imagen 3.
        //
        // Dos campanas de radio rA y rB, con sus centros a distancia LA y LB
        // del centro de la pieza y un ángulo θ entre ejes, tienen sus centros
        // separados por la ley del coseno:
        //     d² = LA² + LB² − 2·LA·LB·cos θ
        // y dejan de tocarse cuando d ≥ rA + rB + holgura.
        //
        // Ojo con θ: `GetAngleTo` da el ángulo entre los vectores de SALIDA, así
        // que θ≈180° son brazos OPUESTOS (un tramo recto: jamás se tocan) y θ
        // pequeño es el caso cerrado. La versión anterior usaba 1/sin(θ), que
        // además de tener la geometría invertida se iba al infinito en θ=180°
        // (de ahí los "alargados a 2998 ft" del log).
        private static void SepararBrazos(List<Brazo> brazos, Editor ed)
        {
            for (int i = 0; i < brazos.Count; i++)
                for (int k = i + 1; k < brazos.Count; k++)
                {
                    var a = brazos[i]; var b = brazos[k];
                    double ang = a.Direccion.GetAngleTo(b.Direccion);
                    double cos = Math.Cos(ang);
                    // Radio EXTERIOR de cada campana.
                    double rA = a.DiamFt / 2.0 + HOLGURA_FT + PARED_FT;
                    double rB = b.DiamFt / 2.0 + HOLGURA_FT + PARED_FT;
                    double minimo = rA + rB + SEPARACION_MIN_FT;

                    // Centro de cada campana, medido desde el centro de la pieza.
                    double cA = a.LargoCuerpoFt + a.DiamFt * LARGO_CAMPANA_D / 2.0;
                    double cB = b.LargoCuerpoFt + b.DiamFt * LARGO_CAMPANA_D / 2.0;
                    double d = Math.Sqrt(Math.Max(0, cA * cA + cB * cB - 2 * cA * cB * cos));
                    if (d >= minimo) continue;               // ya están separadas

                    // Alargar ambos brazos por igual hasta que d alcance el
                    // mínimo. Con cA = cB = c, la ley del coseno se reduce a
                    //     d = c·sqrt(2 − 2·cos θ)
                    // así que el centro de campana necesario es
                    //     c = minimo / sqrt(2 − 2·cos θ).
                    double k2 = Math.Sqrt(Math.Max(1e-9, 2.0 - 2.0 * cos));
                    double cNecesario = minimo / k2;
                    // Corrección por la FORMA de la campana: el cálculo de
                    // arriba trata cada campana como una esfera de radio r, pero
                    // son CILINDROS. Dos cilindros con ángulo cerrado se tocan
                    // antes que dos esferas, porque su propio largo acerca las
                    // aristas. La esquina de cada campana está a
                    // sqrt(r² + (L/2)²) de su centro, no a r, así que se escala
                    // la distancia necesaria por esa relación.
                    double lCampA = a.DiamFt * LARGO_CAMPANA_D;
                    double lCampB = b.DiamFt * LARGO_CAMPANA_D;
                    double esqA = Math.Sqrt(rA * rA + (lCampA / 2) * (lCampA / 2));
                    double esqB = Math.Sqrt(rB * rB + (lCampB / 2) * (lCampB / 2));
                    cNecesario *= (esqA + esqB + SEPARACION_MIN_FT) / minimo;

                    double largoA = cNecesario - lCampA / 2.0;
                    double largoB = cNecesario - lCampB / 2.0;

                    double antesA = a.LargoCuerpoFt, antesB = b.LargoCuerpoFt;
                    a.LargoCuerpoFt = Math.Max(a.LargoCuerpoFt, largoA);
                    b.LargoCuerpoFt = Math.Max(b.LargoCuerpoFt, largoB);
                    ed?.WriteMessage($"\n    [FITTING-SOLIDO] Campanas a {ang * 180.0 / Math.PI:F0}° " +
                        $"separadas {d:F2} ft < mínimo {minimo:F2} ft — brazos " +
                        $"{antesA:F2}/{antesB:F2} → {a.LargoCuerpoFt:F2}/{b.LargoCuerpoFt:F2} ft.");
                }
        }

        // ── Recorte de los tubos ────────────────────────────────────────────
        // Sin esto el tubo entra hasta el fondo del sólido y lo atraviesa. El
        // extremo se DESLIZA sobre su propio eje (nunca se rota: el trazado
        // viene del PDF y es la verdad) hasta quedar dentro de la campana.
        private static void RecortarTubos(
            Transaction tr, Point3d centro, List<Brazo> brazos, Editor ed)
        {
            foreach (var b in brazos)
            {
                if (b.PipeId == ObjectId.Null) continue;
                try
                {
                    var pp = tr.GetObject(b.PipeId, OpenMode.ForWrite)
                             as Autodesk.Civil.DatabaseServices.PressurePipe;
                    if (pp == null) continue;

                    // Punto fijo = extremo LEJANO (el que no toca la juntura).
                    Point3d fijo = (b.Port == 0) ? pp.EndPoint : pp.StartPoint;
                    Vector3d eje = (b.Port == 0) ? (pp.StartPoint - fijo) : (pp.EndPoint - fijo);
                    if (eje.Length < 1e-9) continue;
                    Vector3d u = eje.GetNormal();

                    // Dónde muere el tubo: sobre su propio eje, a `AlcanceTuboFt`
                    // del centro de la pieza. Se resuelve proyectando el centro
                    // sobre la recta del tubo y retrocediendo esa distancia.
                    double tCentro = (centro - fijo).DotProduct(u);
                    double tDestino = tCentro - b.AlcanceTuboFt;
                    // Nunca recortar más allá del extremo lejano (el tubo quedaría
                    // invertido). Pasa con codos cerrados sobre tramos cortos: se
                    // deja el tubo como está y se avisa, en vez de callarlo.
                    if (tDestino <= 0.05)
                    {
                        ed?.WriteMessage($"\n    ⚠ [FITTING-SOLIDO] Tubo de {tCentro:F2} ft demasiado corto " +
                            $"para recortar {b.AlcanceTuboFt:F2} ft junto a la pieza — se deja sin recortar.");
                        continue;
                    }
                    Point3d destino = fijo + u * tDestino;

                    if (b.Port == 0) pp.StartPoint = destino;
                    else pp.EndPoint = destino;
                }
                catch (Exception ex)
                {
                    ed?.WriteMessage($"\n    ⚠ [FITTING-SOLIDO] No se pudo recortar un tubo: {ex.Message}");
                }
            }
        }

        // ── XDATA / property set ────────────────────────────────────────────
        // Datos que el ingeniero civil necesita leer sobre la pieza.
        private static void GrabarXData(
            Database db, Transaction tr, Solid3d pieza, Info info,
            List<Brazo> brazos, Point3d centro, Editor ed)
        {
            if (info == null) return;
            try
            {
                // La app tiene que estar registrada en la RegAppTable ANTES de
                // asignar el XDATA; si no, AutoCAD descarta el ResultBuffer sin
                // lanzar excepción y la pieza queda sin datos.
                var rat = (RegAppTable)tr.GetObject(db.RegAppTableId, OpenMode.ForWrite);
                if (!rat.Has(APP_XDATA))
                {
                    var rar = new RegAppTableRecord { Name = APP_XDATA };
                    rat.Add(rar);
                    tr.AddNewlyCreatedDBObject(rar, true);
                }
                double diamMayor = brazos.Max(b => b.DiamFt) * 12.0;
                double diamMenor = brazos.Min(b => b.DiamFt) * 12.0;
                // Rumbo de cada salida (azimut topográfico: 0°=Norte, horario).
                // Es lo que el ingeniero necesita para replantear la pieza en obra.
                string rumbos = string.Join(";", brazos.Select(b =>
                {
                    double az = Math.Atan2(b.Direccion.X, b.Direccion.Y) * 180.0 / Math.PI;
                    if (az < 0) az += 360.0;
                    return az.ToString("F1");
                }));
                // Pendiente de cada salida, en %. Tee y Wye son rígidas en Z
                // (siempre 0), pero el codo conserva la pendiente de sus tubos,
                // así que aquí es donde se ve si la pieza va inclinada.
                string pendientes = string.Join(";", brazos.Select(b =>
                {
                    double h = Math.Sqrt(b.Direccion.X * b.Direccion.X + b.Direccion.Y * b.Direccion.Y);
                    double p = h > 1e-9 ? (b.Direccion.Z / h) * 100.0 : 0.0;
                    return p.ToString("F2");
                }));
                // Longitud total de la pieza de punta a punta de sus campanas.
                double largoTotal = brazos.Sum(b => b.LargoCuerpoFt + b.DiamFt * LARGO_CAMPANA_D);
                using (var rb = new ResultBuffer(
                    new TypedValue((int)DxfCode.ExtendedDataRegAppName, APP_XDATA),
                    // — Identificación de la pieza —
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"TIPO={info.Tipo}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"ANGULO={info.AnguloDeg:F1}"),
                    // — Dimensiones (para cómputos métricos y pedido de material) —
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"DIAM_PRINCIPAL_IN={diamMayor:F1}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"DIAM_RAMAL_IN={diamMenor:F1}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"N_PUERTOS={brazos.Count}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"LARGO_TOTAL_FT={largoTotal:F2}"),
                    // — Replanteo en obra —
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"COORD_X={centro.X:F3}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"COORD_Y={centro.Y:F3}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"COTA_EJE_FT={centro.Z:F3}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"RUMBOS_SALIDA={rumbos}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"PENDIENTES_PCT={pendientes}"),
                    // — Trazabilidad —
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"MATERIAL={info.Material}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, $"RED={info.Red}"),
                    new TypedValue((int)DxfCode.ExtendedDataAsciiString, "ORIGEN=PDFCAD_SOLIDO")))
                {
                    pieza.XData = rb;
                }
                // Releer: si la app no quedó registrada, AutoCAD descarta el
                // XDATA sin lanzar excepción y la pieza sale sin datos. El
                // resultado se reporta SIEMPRE (no solo al fallar) para poder
                // verificar de un vistazo en el log que los property sets van.
                using (var chk = pieza.GetXDataForApplication(APP_XDATA))
                {
                    if (chk == null)
                        ed?.WriteMessage($"\n    ⚠ [XDATA] La pieza {info.Tipo} quedó SIN " +
                            $"property set (app '{APP_XDATA}' no registrada en el dibujo).");
                    else
                    {
                        int n = chk.AsArray().Count(t =>
                            t.TypeCode == (int)DxfCode.ExtendedDataAsciiString);
                        ed?.WriteMessage($"\n    · [XDATA] {info.Tipo}: {n} campos grabados " +
                            $"(app '{APP_XDATA}') — TIPO={info.Tipo} ANGULO={info.AnguloDeg:F1}°.");
                    }
                }
            }
            catch (Exception ex)
            {
                // No puede quedar en silencio: sin este aviso, una pieza sin
                // property set parece un problema del dibujo y no del plugin.
                ed?.WriteMessage($"\n    ⚠ [FITTING-SOLIDO] No se pudo grabar el XDATA " +
                    $"de la pieza {info.Tipo}: {ex.Message}");
            }
        }

        // ── Geometría de la curva de un codo ────────────────────────────────
        // Radio de eje R y distancia vértice→tangencia T de un codo de
        // diámetro d cuyos brazos forman `ang` (rad) ENTRE EJES. Única fuente
        // de verdad: la usa ConstruirCodo y también quien necesita saber cuánto
        // mide un codo ANTES de construirlo (las conexiones verticales colocan
        // el codo a una distancia exacta de la Wye).
        //
        // Tangencia de un arco inscrito entre dos rectas que forman ángulo
        // `ang`: T = R / tan(ang/2). Con ang≈180° (tramo recto) T→0; con ang
        // pequeño (giro fuerte) T crece: la curva necesita más espacio.
        //
        // Se acota T para que la pieza no se dispare, pero SOLO hasta donde el
        // radio siga siendo viable: nunca por debajo de RADIO_CURVA_MIN_D (o del
        // radio mínimo viable en un codo cerrado). Antes se recalculaba
        // R = T·tan(φ) sin piso y en giros fuertes quedaban radios de 0.4·D o
        // menos: el barrido se auto-intersectaba (eGeneralModelingFailure).
        private static bool CurvaCodo(double d, double ang,
            out double R, out double T, out bool cerrado)
        {
            double giro = Math.PI - ang;
            cerrado = giro > GIRO_CERRADO_DEG * Math.PI / 180.0;
            R = d * RADIO_CURVA_D; T = 0;
            double tanPhi = Math.Tan(ang / 2.0);
            if (Math.Abs(tanPhi) < 1e-9) return false;
            T = R / tanPhi;
            double tMax = d * TANGENCIA_MAX_D;
            if (T > tMax)
            {
                // Codo cerrado: el piso es el radio mínimo VIABLE (el que recorta
                // menos tubería); en el resto se mantiene 1·D.
                double rMin = cerrado ? RadioMinimoViable(d) : d * RADIO_CURVA_MIN_D;
                T = Math.Max(tMax, rMin / tanPhi);
                R = T * tanPhi;
                if (R < rMin - 1e-9) { R = rMin; T = R / tanPhi; }
            }
            return true;
        }

        // Brazo de un codo de diámetro d y ángulo entre ejes `ang`, ya con su
        // largo de cuerpo: sirve para leer BocaFt/AlcanceTuboFt de un codo que
        // todavía no se construyó.
        internal static Brazo BrazoDeCodo(double d, double ang)
        {
            CurvaCodo(d, ang, out _, out double T, out _);
            return new Brazo { DiamFt = d, LargoCuerpoFt = T + d * COLLAR_CODO_D };
        }

        // ── Codo con curva real ─────────────────────────────────────────────
        // Dos cilindros pegados dejan un pico: le falta la curva, que es la
        // parte característica de la pieza. Aquí el cuerpo se genera barriendo
        // un círculo (la sección del tubo) a lo largo de una trayectoria
        // recta → arco → recta, y luego se le añaden las dos campanas.
        //
        //        campana                                campana
        //           ╔═╗                                   ╔═╗
        //           ║ ╠═══ recta ═══╗                     ║ ║
        //           ╚═╝              ╚══ arco ══╗    ╔════╣ ║
        //                                        ╚═══╝    ╚═╝
        //
        // El arco es TANGENTE a los dos ejes, con centro sobre la bisectriz.
        // Con semiángulo φ entre los ejes y radio de curvatura R, la tangencia
        // cae a T = R/tan(φ) del vértice.
        private static Solid3d ConstruirCodo(Point3d centro, Brazo a, Brazo b, Editor ed)
        {
            try
            {
                if (a.DiamFt <= 1e-6 || b.DiamFt <= 1e-6) return null;
                // Codo REDUCTOR si los diámetros difieren: el cuerpo se estrecha
                // de uno a otro a lo largo del barrido (ver ScaleFactor abajo).
                bool reductor = Math.Abs(a.DiamFt - b.DiamFt) > 1e-6;

                Vector3d dA = a.Direccion.GetNormal(), dB = b.Direccion.GetNormal();
                // Ángulo ENTRE LOS EJES de los dos brazos. Ambos vectores nacen
                // en el centro de la pieza y apuntan hacia sus tubos, así que:
                //   ang ≈ 180° → los brazos son opuestos = tramo RECTO
                //   ang pequeño → la tubería vuelve sobre sí misma = giro fuerte
                // La deflexión del flujo (lo que dobla el codo) es el suplemento.
                double ang = dA.GetAngleTo(dB);
                double giro = Math.PI - ang;             // deflexión del flujo
                if (giro < 2.0 * Math.PI / 180.0) return null;   // casi recto

                // El semiángulo para la tangencia se mide sobre los EJES, que es
                // el ángulo que forman los dos tramos rectos entre sí.
                if (ed != null)
                    ed.WriteMessage($"\n    [CODO-DBG] ejes a {ang * 180.0 / Math.PI:F1}° " +
                        $"→ deflexión {giro * 180.0 / Math.PI:F1}°, " +
                        (reductor ? $"REDUCTOR Ø{a.DiamFt * 12.0:F0}\"→Ø{b.DiamFt * 12.0:F0}\"."
                                  : $"Ø{a.DiamFt * 12.0:F0}\"."));
                // Tubos literalmente uno encima del otro: no hay curva posible
                // (la tangencia se iría al infinito). Es un error del trazado.
                if (ang < ANG_EJES_MIN_DEG * Math.PI / 180.0)
                {
                    ed?.WriteMessage($"\n    ⚠ [FITTING-SOLIDO] Los dos tubos van casi superpuestos " +
                        $"({ang * 180.0 / Math.PI:F1}° entre ejes) — revisa el trazado; se arma con tramos rectos.");
                    return null;
                }

                // Codo CERRADO: la tubería vuelve casi sobre sí misma (codo de
                // retorno). Antes se abandonaba la curva y se armaban dos tramos
                // rectos desde el vértice, que se pisaban entre sí y con los
                // tubos. Ahora se hace la curva igual, con el radio más cerrado
                // que no se superpone consigo misma ni choca campana con campana,
                // y los tubos se RECORTAN hasta donde esa curva cabe. La curva ya
                // no llega al vértice original: gira antes, como un codo real.
                // En un reductor la curva se dimensiona con el diámetro MAYOR:
                // tiene que caber el tubo grueso.
                double d = Math.Max(a.DiamFt, b.DiamFt);
                double phi = ang / 2.0;
                if (!CurvaCodo(d, ang, out double R, out double T, out bool cerrado)) return null;

                // El tramo recto de un codo solo tiene que llegar al punto de
                // tangencia más un pequeño collar para la campana. NO se le
                // aplica LARGO_BRAZO_D (1.25·D): ese mínimo está pensado para
                // los brazos rectos de una Y, y en un codo estiraba la pieza
                // muy por encima de lo real (un codo de giro cerrado llegaba a
                // 4.6·D de largo). Un codo de fundición mide ~1.5–2·D en total.
                double largoA = T + a.DiamFt * COLLAR_CODO_D;
                double largoB = T + b.DiamFt * COLLAR_CODO_D;
                a.LargoCuerpoFt = largoA; b.LargoCuerpoFt = largoB;

                if (cerrado)
                {
                    double giroAntes = R / Math.Sin(phi) - R;   // vértice → punto más cercano de la curva
                    ed?.WriteMessage($"\n    [FITTING-SOLIDO] Codo cerrado (deflexión {giro * 180.0 / Math.PI:F0}°): " +
                        $"radio mínimo viable R={R:F3} ft ({R / d:F2}·D); los tubos se recortan " +
                        $"~{a.AlcanceTuboFt:F2} ft desde el vértice y la curva gira {giroAntes:F2} ft antes de él.");
                }

                Point3d pA = centro + dA * largoA;       // fin del tramo recto A
                Point3d pB = centro + dB * largoB;       // fin del tramo recto B
                Point3d tA = centro + dA * T;            // tangencia sobre el eje A
                Point3d tB = centro + dB * T;            // tangencia sobre el eje B

                // Trayectoria: pA → tA → (arco) → tB → pB, con bulge en el
                // vértice. El bulge de un arco que gira `giro` es tan(giro/4).
                //
                // La polilínea se construye en el PLANO PROPIO del codo (el que
                // contienen sus dos direcciones), no en el plano XY del dibujo.
                // Un codo entre tubos a distinta cota es un plano inclinado; si
                // se forzara a XY (con `Elevation`), la Z de los brazos se
                // perdería y la pieza saldría horizontal, despegada de sus tubos.
                Vector3d normal = dA.CrossProduct(dB);
                if (normal.Length < 1e-9) return null;    // ejes paralelos
                normal = normal.GetNormal();

                // Los vértices de una Polyline van en coordenadas OCS, cuya base
                // AutoCAD deriva de `Normal` con el algoritmo del Eje
                // Arbitrario. Hay que replicarlo exactamente y proyectar desde
                // el ORIGEN del WCS (no desde el centro de la pieza: las
                // coordenadas OCS son absolutas, no relativas).
                Vector3d ex, ey;
                EjeArbitrario(normal, out ex, out ey);
                Func<Point3d, Point2d> aOcs = p =>
                {
                    var v = new Vector3d(p.X, p.Y, p.Z);
                    return new Point2d(v.DotProduct(ex), v.DotProduct(ey));
                };

                // Signo del bulge = sentido del giro MEDIDO EN LA BASE OCS. El
                // recorrido va tA→tB, así que se compara la dirección entrante
                // (dA) con la saliente (−dB) proyectadas en esa base.
                double giroOcs = Math.Atan2(
                    dA.DotProduct(ex) * (-dB).DotProduct(ey) - dA.DotProduct(ey) * (-dB).DotProduct(ex),
                    dA.DotProduct(ex) * (-dB).DotProduct(ex) + dA.DotProduct(ey) * (-dB).DotProduct(ey));
                double bulge = Math.Tan(giroOcs / 4.0);

                using (var path = new Polyline())
                {
                    path.Normal = normal;
                    path.AddVertexAt(0, aOcs(pA), 0, 0, 0);
                    path.AddVertexAt(1, aOcs(tA), bulge, 0, 0);
                    path.AddVertexAt(2, aOcs(tB), 0, 0, 0);
                    path.AddVertexAt(3, aOcs(pB), 0, 0, 0);
                    // Distancia del plano al origen, medida sobre la normal.
                    path.Elevation = new Vector3d(centro.X, centro.Y, centro.Z).DotProduct(normal);

                    // Sección: círculo del diámetro del brazo A, perpendicular al
                    // inicio de la trayectoria (Sweep lo alinea solo). En un codo
                    // reductor, ScaleFactor la escala linealmente a lo largo del
                    // barrido hasta llegar al diámetro del brazo B en pB.
                    using (var perfil = new Circle(pA, dA, a.DiamFt / 2.0))
                    {
                        var ob = new SweepOptionsBuilder
                        {
                            Align = SweepOptionsAlignOption.AlignSweepEntityToPath,
                            BasePoint = pA,
                            Bank = false,
                        };
                        if (reductor) ob.ScaleFactor = b.DiamFt / a.DiamFt;
                        var opts = ob.ToSweepOptions();

                        var cuerpo = new Solid3d();
                        cuerpo.CreateSweptSolid(perfil, path, opts);

                        // Campanas en los dos extremos. Se MONTAN sobre el
                        // cuerpo (arrancan un poco antes de su punta) en vez de
                        // apoyarse en su cara: dos sólidos que solo se rozan en
                        // un plano dejan un escalón/hueco al unirlos, que es el
                        // defecto que se veía en el arranque del arco.
                        foreach (var (br, punta, dir) in new[] { (a, pA, dA), (b, pB, dB) })
                        {
                            double rCamp = br.DiamFt / 2.0 + HOLGURA_FT + PARED_FT;
                            double lCamp = br.DiamFt * LARGO_CAMPANA_D;
                            double monta = br.DiamFt * MONTAJE_CAMPANA_D;
                            Point3d ini = punta - dir * monta;        // arranque solapado
                            var camp = Cilindro(rCamp, lCamp + monta,
                                                ini + dir * ((lCamp + monta) / 2.0), dir);
                            if (camp == null) continue;
                            try { cuerpo.BooleanOperation(BooleanOperationType.BoolUnite, camp); }
                            catch { try { camp.Dispose(); } catch { } }
                        }
                        // El tubo muere donde empieza la campana + el calado.
                        a.LargoCuerpoFt = largoA; b.LargoCuerpoFt = largoB;
                        return cuerpo;
                    }
                }
            }
            catch (Exception ex)
            {
                ed?.WriteMessage($"\n    [FITTING-SOLIDO] Codo curvo falló ({ex.Message}) — se usa el recto.");
                return null;
            }
        }

        // Algoritmo del Eje Arbitrario de AutoCAD: dada la normal de un plano,
        // devuelve la base (ex, ey) que el propio AutoCAD usará para
        // interpretar las coordenadas OCS de una entidad con esa normal. Hay
        // que replicarlo tal cual; una base propia deja la geometría girada
        // dentro de su plano.
        private static void EjeArbitrario(Vector3d n, out Vector3d ex, out Vector3d ey)
        {
            const double LIMITE = 1.0 / 64.0;
            Vector3d baseRef = (Math.Abs(n.X) < LIMITE && Math.Abs(n.Y) < LIMITE)
                ? Vector3d.YAxis : Vector3d.ZAxis;
            ex = baseRef.CrossProduct(n).GetNormal();
            ey = n.CrossProduct(ex).GetNormal();
        }

        // Un brazo = cuerpo (Ø del tubo) + campana en el extremo (Ø mayor, para
        // que la punta del tubo entre dentro).
        private static Solid3d ConstruirBrazo(Point3d centro, Brazo b)
        {
            if (b.DiamFt <= 1e-6) return null;
            Vector3d dir = b.Direccion;
            if (dir.Length < 1e-9) return null;
            dir = dir.GetNormal();

            double rTubo = b.DiamFt / 2.0;
            double largoCuerpo = b.LargoCuerpoFt > 1e-9 ? b.LargoCuerpoFt : b.DiamFt * LARGO_BRAZO_D;
            double largoCampana = b.DiamFt * LARGO_CAMPANA_D;
            double rCampana = rTubo + HOLGURA_FT + PARED_FT;

            // Cuerpo: del centro de la juntura hasta donde empieza la campana.
            // El tronco de una Y lo lleva un poco más grueso (EngroseFt).
            Solid3d cuerpo = Cilindro(rTubo + b.EngroseFt, largoCuerpo,
                                      centro + dir * (largoCuerpo / 2.0), dir);
            if (cuerpo == null) return null;

            // Campana: concéntrica y más gruesa, MONTADA sobre el final del
            // cuerpo (no apoyada en su cara) para que la unión booleana no deje
            // un escalón entre ambos sólidos.
            double monta = b.DiamFt * MONTAJE_CAMPANA_D;
            Solid3d campana = Cilindro(rCampana, largoCampana + monta,
                                       centro + dir * (largoCuerpo - monta + (largoCampana + monta) / 2.0), dir);
            if (campana == null) return cuerpo;

            try { cuerpo.BooleanOperation(BooleanOperationType.BoolUnite, campana); }
            catch { try { campana.Dispose(); } catch { } }
            return cuerpo;
        }

        // Cilindro macizo de radio r y altura h, centrado en `centro` y con su
        // eje alineado a `dir` (unitario). Mismo patrón que los conductos de
        // bancoducto en ImportarRed.cs: CreateFrustum nace en el origen sobre
        // el eje Z, luego se traslada y se rota.
        private static Solid3d Cilindro(double r, double h, Point3d centro, Vector3d dir)
        {
            if (r <= 1e-9 || h <= 1e-9) return null;
            var cyl = new Solid3d();
            try
            {
                cyl.CreateFrustum(h, r, r, r);
                cyl.TransformBy(Matrix3d.Displacement(centro - Point3d.Origin));
                Vector3d cross = Vector3d.ZAxis.CrossProduct(dir);
                double dot = Vector3d.ZAxis.DotProduct(dir);
                if (cross.Length > 1e-9)
                {
                    double ang = Math.Acos(Math.Max(-1, Math.Min(1, dot)));
                    cyl.TransformBy(Matrix3d.Rotation(ang, cross.GetNormal(), centro));
                }
                else if (dot < 0)
                {
                    cyl.TransformBy(Matrix3d.Rotation(Math.PI, Vector3d.XAxis, centro));
                }
                return cyl;
            }
            catch
            {
                try { cyl.Dispose(); } catch { }
                return null;
            }
        }

        // Lee el property set de un Solid3d generado por el plugin. Devuelve
        // las líneas "CLAVE=valor", o null si la pieza no lo tiene.
        internal static List<string> LeerXData(Entity ent)
        {
            try
            {
                using (ResultBuffer rb = ent?.GetXDataForApplication(APP_XDATA))
                {
                    if (rb == null) return null;
                    var datos = new List<string>();
                    foreach (TypedValue tv in rb)
                        if (tv.TypeCode == (int)DxfCode.ExtendedDataAsciiString)
                            datos.Add(tv.Value?.ToString() ?? "");
                    return datos.Count > 0 ? datos : null;
                }
            }
            catch { return null; }
        }

        private static void AsegurarCapa(Database db, Transaction tr)
        {
            try
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                if (lt.Has(CAPA)) return;
                lt.UpgradeOpen();
                using (var ltr = new LayerTableRecord { Name = CAPA })
                {
                    lt.Add(ltr);
                    tr.AddNewlyCreatedDBObject(ltr, true);
                }
            }
            catch { }
        }
    }
}
