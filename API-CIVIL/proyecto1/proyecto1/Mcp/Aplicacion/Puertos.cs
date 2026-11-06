using System;
using System.Collections.Generic;
using Civil3DBasico.Mcp.Dominio;

// ============================================================================
//  PUERTOS de la capa de Aplicación (PUROS). Los implementa Infraestructura con
//  la API de Civil 3D (y las pruebas con dobles en memoria). Las implementaciones
//  se encargan de ir al hilo de AutoCAD y de bloquear el documento: Aplicación
//  no sabe nada de hilos ni de Autodesk.
// ============================================================================

namespace Civil3DBasico.Mcp.Aplicacion
{
    public interface IModeloLector
    {
        EstadoDibujo Estado();
        /// <summary>Foto del modelo (la implementación puede cachearla hasta que el dibujo cambie).</summary>
        Modelo Leer();
        /// <summary>Datos extra de un elemento (Property Sets, conexiones…); null si no existe.</summary>
        Dictionary<string, object> Detalle(string handle);
        bool CapaExiste(string capa);
        /// <summary>Tubos de la lista de piezas de la red de esa tubería (para cambiar su tamaño o material).</summary>
        List<TamanoDisponible> Tamanos(string handleTuberia);
        /// <summary>Los cuerpos 3D del dibujo (tuberías, estructuras, accesorios, sólidos) con su caja.</summary>
        List<Cuerpo> Cuerpos();
        /// <summary>De esos pares (handles), los que de verdad se interfieren (sólidos de Civil 3D).</summary>
        List<Interferencia> Interferencias(IList<(string a, string b)> pares);
    }

    public interface IEditorDibujo
    {
        /// <summary>Aplica el cambio en el dibujo (deshacible). Lanza excepción con un
        /// mensaje claro si no se puede (p. ej. Civil 3D ocupado en un comando).</summary>
        void Aplicar(CambioPropuesto cambio);
        /// <summary>Encuadra y selecciona; devuelve cuántos encontró.</summary>
        int IrA(IReadOnlyList<string> handles);
    }

    public interface IRegistroCambios
    {
        void Anotar(RegistroCambio r);
        List<RegistroCambio> Ultimos(int n);
    }
}
