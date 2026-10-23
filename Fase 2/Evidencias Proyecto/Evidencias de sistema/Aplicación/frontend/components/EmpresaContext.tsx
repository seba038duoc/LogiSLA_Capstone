"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { Empresa, listarEmpresas, mensajeDeError } from "@/lib/api";

/**
 * Empresa activa de la sesión.
 *
 * Todavía no hay login (queda para otro sprint), así que la empresa se
 * elige en la cabecera y se recuerda en este navegador. Cuando exista
 * autenticación, este contexto es el único lugar que hay que cambiar:
 * el resto de la app solo pregunta `useEmpresa().empresa`.
 */

const CLAVE_GUARDADO = "logisla.empresa_id";

type ValorContexto = {
  empresas: Empresa[];
  empresa: Empresa | null;
  cargando: boolean;
  error: string | null;
  elegirEmpresa: (id: string) => void;
  reintentar: () => void;
};

const ContextoEmpresa = createContext<ValorContexto | null>(null);

function leerGuardado(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_GUARDADO);
  } catch {
    return null; // navegador con almacenamiento bloqueado: se sigue sin recordar
  }
}

function guardar(id: string) {
  try {
    window.localStorage.setItem(CLAVE_GUARDADO, id);
  } catch {
    // ídem: no es crítico
  }
}

export function ProveedorEmpresa({ children }: { children: React.ReactNode }) {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [idElegido, setIdElegido] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [intento, setIntento] = useState(0);

  useEffect(() => {
    let vigente = true;
    listarEmpresas()
      .then((lista) => {
        if (!vigente) return;
        setEmpresas(lista);
        const guardado = leerGuardado();
        const inicial = lista.find((e) => e.id === guardado) ?? lista[0] ?? null;
        setIdElegido(inicial ? inicial.id : null);
        setError(null);
      })
      .catch((e) => {
        if (vigente) setError(mensajeDeError(e));
      })
      .finally(() => {
        if (vigente) setCargando(false);
      });
    return () => {
      vigente = false;
    };
  }, [intento]);

  const elegirEmpresa = useCallback((id: string) => {
    setIdElegido(id);
    guardar(id);
  }, []);

  const reintentar = useCallback(() => {
    setCargando(true);
    setError(null);
    setIntento((n) => n + 1);
  }, []);

  const valor = useMemo<ValorContexto>(
    () => ({
      empresas,
      empresa: empresas.find((e) => e.id === idElegido) ?? null,
      cargando,
      error,
      elegirEmpresa,
      reintentar,
    }),
    [empresas, idElegido, cargando, error, elegirEmpresa, reintentar]
  );

  return <ContextoEmpresa.Provider value={valor}>{children}</ContextoEmpresa.Provider>;
}

export function useEmpresa(): ValorContexto {
  const valor = useContext(ContextoEmpresa);
  if (!valor) throw new Error("useEmpresa debe usarse dentro de <ProveedorEmpresa>");
  return valor;
}
