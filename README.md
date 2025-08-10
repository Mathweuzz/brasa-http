# BrasaHTTP 🔥

Servidor web **minimalista**, feito do zero, só com a **biblioteca padrão** do Python.

## Filosofia
- **Zero (ou quase zero) dependências externas**
- **Didático**: cada passo ensina um conceito e mantém o código claro
- **Seguro o suficiente** para estudo/doméstico, com boas práticas essenciais

## Estrutura (inicial)brasa-http/
├─ app/
│ ├─ init.py
│ ├─ server.py # (nasce no Passo 2)
│ ├─ router.py # (Passo 3)
│ ├─ responses.py # (Passo 3/4/5)
│ ├─ templates/
│ └─ static/
├─ config/
├─ data/
├─ scripts/
├─ tests/
├─ .gitignore
├─ LICENSE
└─ README.md## Roteiro
1. Ambiente e scaffolding (este)
2. Hello TCP/HTTP com `socket`
3. Parsing da requisição + roteamento básico
4. Estáticos com segurança
5. Templates sem libs externas
6. Query string, POST/formulários
7. Cookies e sessões assinadas
8. Concorrência (threads/asyncio)
9. Persistência `sqlite3`
10. Logging/config/estrutura limpa
11. gzip/chunked (opcional)
12. HTTPS local (`ssl`)
13. Domínio e DNS
14. Expor servidor em casa (NAT/port-forwarding)
15. TLS válido (Let's Encrypt)
16. Endurecimento (headers, rate-limit simples)
17. Rodar como serviço (systemd)
18. Construir o site real
