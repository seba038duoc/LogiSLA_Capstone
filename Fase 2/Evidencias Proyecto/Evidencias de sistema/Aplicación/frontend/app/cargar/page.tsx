"use client";

import UploadFlow from "@/components/UploadFlow";
import { ConEmpresa } from "@/components/EstadoEmpresa";

export default function PaginaCargar() {
  return (
    <main className="mx-auto w-full max-w-6xl flex-1 px-5 py-10">
      <ConEmpresa>{(empresa) => <UploadFlow key={empresa.id} empresa={empresa} />}</ConEmpresa>
    </main>
  );
}
