using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  ADAPTADOR de lectura: las ANOTACIONES del espacio modelo (textos, MLEADER,
//  LEADER, cotas, tramas) con sus cajas en planta, y los accesorios SÓLIDOS del
//  plugin (XDATA PDFCAD_FITTING). Todo en una pasada por el espacio modelo.
// ============================================================================

namespace Civil3DBasico.Mcp.Infraestructura
{
    using Caja = Civil3DBasico.Mcp.Dominio.Caja;
    using Leader = Autodesk.AutoCAD.DatabaseServices.Leader;

    internal sealed partial class Civil3DLector
    {
        private static void LeerAnotaciones(Transaction tr, Database db, Modelo m)
        {
            var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
            RXClass cTexto = RXObject.GetClass(typeof(DBText)), cMText = RXObject.GetClass(typeof(MText)),
                    cSolido = RXObject.GetClass(typeof(Solid3d)), cML = RXObject.GetClass(typeof(MLeader)),
                    cLeader = RXObject.GetClass(typeof(Leader)), cCota = RXObject.GetClass(typeof(Dimension)),
                    cTrama = RXObject.GetClass(typeof(Hatch));
            foreach (ObjectId id in ms)
            {
                try
                {
                    RXClass k = id.ObjectClass;
                    if (k.IsDerivedFrom(cSolido))
                    {
                        if (tr.GetObject(id, OpenMode.ForRead) is Solid3d so && Solido(so) is Accesorio acc) m.Accesorios.Add(acc);
                    }
                    else if (k.IsDerivedFrom(cTexto) && tr.GetObject(id, OpenMode.ForRead) is DBText t)
                        m.Textos.Add(new TextoDibujo
                        {
                            Handle = t.Handle.ToString(), Tipo = "TEXT", Contenido = t.TextString, Capa = t.Layer,
                            X = t.Position.X, Y = t.Position.Y, Altura = t.Height, Caja = CajaDe(t),
                        });
                    else if (k.IsDerivedFrom(cMText) && tr.GetObject(id, OpenMode.ForRead) is MText mt)
                        m.Textos.Add(new TextoDibujo
                        {
                            Handle = mt.Handle.ToString(), Tipo = "MTEXT", Contenido = mt.Text, Capa = mt.Layer,
                            X = mt.Location.X, Y = mt.Location.Y, Altura = mt.TextHeight, Caja = CajaDe(mt), Mascara = mt.BackgroundFill,
                        });
                    else if (k.IsDerivedFrom(cML) && tr.GetObject(id, OpenMode.ForRead) is MLeader ml)
                        LeerMLeader(ml, m);
                    else if (k.IsDerivedFrom(cLeader) && tr.GetObject(id, OpenMode.ForRead) is Leader ld)
                    {
                        var g = new Guia { Handle = ld.Handle.ToString(), Tipo = "LEADER", Capa = ld.Layer, ConTexto = !ld.Annotation.IsNull,
                                           TextoHandle = ld.Annotation.IsNull ? null : ld.Annotation.Handle.ToString() };
                        for (int i = 0; i < ld.NumVertices; i++) { Point3d p = ld.VertexAt(i); g.Vertices.Add((p.X, p.Y)); }
                        m.Guias.Add(g);
                    }
                    else if (k.IsDerivedFrom(cCota) && tr.GetObject(id, OpenMode.ForRead) is Dimension d)
                        m.Cotas.Add(CotaDe(d));
                    else if (k.IsDerivedFrom(cTrama) && tr.GetObject(id, OpenMode.ForRead) is Hatch h)
                        m.Tramas.Add(new Trama { Handle = h.Handle.ToString(), Capa = h.Layer, Patron = h.PatternName, Caja = CajaDe(h) });
                }
                catch { }
            }
        }

        private static Caja CajaDe(Entity e)
        {
            try { Extents3d x = e.GeometricExtents; return new Caja(x.MinPoint.X, x.MinPoint.Y, x.MaxPoint.X, x.MaxPoint.Y); }
            catch { return default; }
        }

        /// <summary>El MLEADER: su texto (como un texto más, con su caja) y sus guías.</summary>
        private static void LeerMLeader(MLeader ml, Modelo m)
        {
            string h = ml.Handle.ToString();
            bool conTexto = false;
            if (ml.ContentType == ContentType.MTextContent && ml.MText is MText mt && !string.IsNullOrWhiteSpace(mt.Text))
            {
                conTexto = true;
                double alto = mt.TextHeight > 0 ? mt.TextHeight : 0.2;
                double ancho = mt.ActualWidth > 0 ? mt.ActualWidth : Math.Max(mt.Text.Length, 1) * alto * 0.6;
                double altoT = mt.ActualHeight > 0 ? mt.ActualHeight : alto * (mt.Text.Count(c => c == '\n') + 1) * 1.4;
                Point3d p = ml.TextLocation;
                // el punto del texto según su anclaje (izquierda/centro/derecha, arriba/medio/abajo)
                string an = mt.Attachment.ToString();
                double x0 = an.EndsWith("Right") ? p.X - ancho : an.EndsWith("Center") ? p.X - ancho / 2 : p.X;
                double y1 = an.StartsWith("Bottom") ? p.Y + altoT : an.StartsWith("Middle") ? p.Y + altoT / 2 : p.Y;
                m.Textos.Add(new TextoDibujo
                {
                    Handle = h, Tipo = "MLEADER", Contenido = mt.Text, Capa = ml.Layer, X = p.X, Y = p.Y, Altura = alto,
                    Caja = new Caja(x0, y1 - altoT, x0 + ancho, y1), Mascara = mt.BackgroundFill,
                });
            }
            try
            {
                foreach (int li in ml.GetLeaderIndexes())
                    foreach (int ll in ml.GetLeaderLineIndexes(li))
                    {
                        var g = new Guia { Handle = h, Tipo = "MLEADER", Capa = ml.Layer, ConTexto = conTexto, TextoHandle = h };
                        int n = ml.VerticesCount(ll);
                        for (int i = 0; i < n; i++) { Point3d v = ml.GetVertex(ll, i); g.Vertices.Add((v.X, v.Y)); }
                        if (g.Vertices.Count > 0) m.Guias.Add(g);
                    }
            }
            catch { }
        }

        private static Cota CotaDe(Dimension d)
        {
            var c = new Cota { Handle = d.Handle.ToString(), Tipo = d.GetType().Name, Capa = d.Layer, Estilo = d.DimensionStyleName };
            try { c.Medida = d.Measurement; } catch { }
            try { c.Decimales = d.Dimdec; c.Flecha = d.Dimasz * Math.Max(d.Dimscale, 1e-9); c.AlturaTexto = d.Dimtxt * Math.Max(d.Dimscale, 1e-9); } catch { }
            string ov = d.DimensionText ?? "";
            string med = Math.Round(c.Medida, Math.Max(c.Decimales, 0)).ToString("F" + Math.Max(c.Decimales, 0), System.Globalization.CultureInfo.InvariantCulture);
            c.Texto = ov.Length == 0 || ov == "<>" ? med : ov.Replace("<>", med).Replace("\\P", " ");
            double h = c.AlturaTexto > 0 ? c.AlturaTexto : 0.2, w = Math.Max(c.Texto.Length, 1) * h * 0.6;
            Point3d tp = d.TextPosition;
            double ang = 0;
            if (d is AlignedDimension ad)
            {
                Vector3d u = ad.XLine2Point - ad.XLine1Point;
                ang = Math.Atan2(u.Y, u.X);
                Vector3d n = new Vector3d(-u.Y, u.X, 0).GetNormal();
                double off = (ad.DimLinePoint - ad.XLine1Point).DotProduct(n);
                c.A = (ad.XLine1Point.X + n.X * off, ad.XLine1Point.Y + n.Y * off);
                c.B = (ad.XLine2Point.X + n.X * off, ad.XLine2Point.Y + n.Y * off);
            }
            else if (d is RotatedDimension rd)
            {
                ang = rd.Rotation;
                var u = new Vector3d(Math.Cos(ang), Math.Sin(ang), 0);
                var n = new Vector3d(-u.Y, u.X, 0);
                double off = (rd.DimLinePoint - rd.XLine1Point).DotProduct(n);
                double t1 = (rd.XLine1Point - Point3d.Origin).DotProduct(u), t2 = (rd.XLine2Point - Point3d.Origin).DotProduct(u);
                double b = (rd.DimLinePoint - Point3d.Origin).DotProduct(n);
                c.A = (u.X * t1 + n.X * b, u.Y * t1 + n.Y * b);
                c.B = (u.X * t2 + n.X * b, u.Y * t2 + n.Y * b);
                _ = off;
            }
            else c.A = c.B = (tp.X, tp.Y);
            // caja del texto: rectángulo w × h centrado en TextPosition, girado con la cota
            double cs = Math.Abs(Math.Cos(ang)), sn = Math.Abs(Math.Sin(ang));
            double hx = (w * cs + h * sn) / 2, hy = (w * sn + h * cs) / 2;
            c.CajaTexto = new Caja(tp.X - hx, tp.Y - hy, tp.X + hx, tp.Y + hy);
            return c;
        }
    }
}
