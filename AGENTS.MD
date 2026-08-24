Você está trabalhando no projeto OpenOmada.

Além dos requisitos técnicos da implementação, siga obrigatoriamente uma
disciplina de Git/GitFlow durante todo o trabalho.

O objetivo é produzir um histórico de commits:

- incremental;
- revisável;
- semanticamente organizado;
- fácil de bisectar;
- fácil de reverter;
- fácil de revisar em Pull Request.

NÃO coloque toda a implementação em um único commit.

======================================================================
REGRA PRINCIPAL
======================================================================

A implementação deve ser dividida em commits pequenos e semanticamente
coerentes.

Um commit deve representar UMA mudança lógica compreensível.

Exemplos bons:

feat(protocol): add ECSP WLAN config message models

feat(wlan): add wireless network domain models

feat(openwrt): add UCI WLAN adapter

feat(vlan): add SSID VLAN reconciliation

feat(client): add unified wireless client state

feat(dhcp): integrate client DHCP lease tracking

feat(portal): add unauthenticated client policy model

feat(portal): add nftables captive enforcement

feat(portal): implement authentication session lifecycle

feat(radius): add portal RADIUS authentication

feat(inform): report WLAN and client state

test(portal): cover authenticated client lifecycle

docs(protocol): document WLAN message mappings

Exemplo RUIM:

feat: implement wlan lan dhcp portal adoption

Outro exemplo RUIM:

wip

Outro exemplo RUIM:

fix stuff

======================================================================
BRANCHING
======================================================================

Não trabalhe diretamente em main/master.

Antes de alterar código:

1. identifique a branch principal do projeto;
2. verifique se o repositório já possui convenção de branches;
3. siga a convenção existente quando houver.

Se não houver uma convenção explícita, crie uma branch de feature:

feature/omada-network-management

ou, se a implementação for grande demais e o projeto permitir branches
intermediárias:

feature/omada-network-management
feature/omada-wlan
feature/omada-captive-portal
feature/omada-lan-dhcp

Prefira UMA branch principal de feature quando todas as camadas precisarem ser
entregues juntas em um único PR.

Não crie branches desnecessárias apenas para parecer organizado.

======================================================================
ANTES DE COMEÇAR
======================================================================

Execute:

git status
git branch --show-current
git log --oneline --decorate -20

Entenda:

- branch atual;
- estado da árvore;
- commits recentes;
- padrão de mensagens de commit;
- existência de mudanças locais anteriores ao seu trabalho.

NUNCA sobrescreva ou inclua em seus commits alterações do usuário que já
estavam no working tree antes da sua implementação.

Se existirem mudanças preexistentes:

- identifique-as;
- preserve-as;
- não faça reset;
- não descarte;
- não misture nos seus commits.

======================================================================
PLANO DE COMMITS
======================================================================

Antes de implementar, defina internamente uma sequência esperada de commits.

Para esta tarefa, uma boa referência seria algo próximo a:

1. architecture/domain models
2. protocol message mapping
3. platform capabilities
4. WLAN configuration
5. VLAN/LAN
6. client state
7. DHCP tracking
8. captive portal policy
9. captive portal enforcement
10. portal session/authentication
11. RADIUS
12. Inform/telemetry
13. integration wiring
14. regression fixes
15. tests
16. documentation

NÃO precisa seguir exatamente esta lista.

A divisão deve acompanhar a arquitetura real encontrada no projeto.

======================================================================
COMMITS DEVEM SER EXECUTÁVEIS
======================================================================

Sempre que possível, cada commit deve:

- compilar;
- não quebrar a suíte existente;
- conter os testes necessários à mudança;
- não depender de código incompleto de commits futuros para funcionar.

Evite commits como:

commit 1:
adiciona chamadas para classes que ainda não existem

commit 2:
adiciona as classes

Prefira uma unidade vertical funcional.

Exemplo:

feat(wlan): add SSID domain model and config parser

inclui:

- model;
- parser;
- validation;
- unit tests.

Depois:

feat(openwrt): apply SSID configuration through UCI

inclui:

- adapter;
- reconciliation;
- platform tests.

======================================================================
TESTES E COMMITS
======================================================================

Testes relacionados à funcionalidade devem preferencialmente estar no MESMO
commit que a funcionalidade.

Exemplo correto:

feat(dhcp): track DHCP leases for wireless clients

contém:

src/...
tests/...

Não faça:

commit:
feat(dhcp): implement DHCP

e cinco commits depois:

test: tests for DHCP

a menos que exista uma razão real.

======================================================================
CONVENTIONAL COMMITS
======================================================================

Se o projeto já possui padrão de commits, siga-o.

Caso contrário, use Conventional Commits.

Tipos permitidos normalmente:

feat:
fix:
refactor:
test:
docs:
chore:
build:
ci:
perf:

Use scope quando fizer sentido:

feat(wlan):
feat(portal):
feat(dhcp):
feat(vlan):
feat(protocol):
feat(openwrt):
feat(inform):
fix(adoption):
test(portal):

Mensagens devem ser imperativas e descrever a mudança.

BOM:

feat(portal): add nftables unauthenticated client enforcement

RUIM:

feat(portal): added portal things

======================================================================
NÃO FAÇA COMMITS GIGANTES
======================================================================

Evite commits que:

- alterem dezenas de arquivos sem necessidade;
- misturem refactor com feature;
- misturem WLAN e Portal sem dependência real;
- mudem formatting em arquivos não relacionados;
- alterem APIs e implementação simultaneamente sem necessidade;
- incluam arquivos gerados;
- incluam dumps do firmware;
- incluam arquivos temporários da engenharia reversa.

Um commit grande é aceitável somente quando a mudança é naturalmente atômica.

Quantidade de linhas não é o critério principal.

Coerência lógica é.

======================================================================
SEPARAR REFACTOR DE FEATURE
======================================================================

Se precisar refatorar código existente para implementar a feature:

primeiro faça, quando possível:

refactor(...): prepare ... for ...

Depois implemente a funcionalidade:

feat(...): implement ...

Isso torna o histórico revisável.

Exemplo:

refactor(client): centralize client state representation

depois:

feat(dhcp): merge DHCP lease data into client state

Evite:

feat(dhcp): refactor client module and add dhcp and rename everything

======================================================================
FORMATTING
======================================================================

Não faça alterações de formatting global no meio da feature.

Se formatter/linter alterar muitos arquivos:

- limite-o aos arquivos modificados;
- ou faça commit separado;
- somente se realmente necessário.

Não misture:

500 linhas de prettier/formatting

com:

20 linhas de mudança funcional.

======================================================================
COMMITS DE ENGENHARIA REVERSA
======================================================================

NÃO faça commit de:

EAP650-filesystem.squashfs

ELFs extraídos

.ko extraídos

strings dumps

Ghidra projects

objdump temporários

captures temporárias

a menos que esses arquivos já façam intencionalmente parte do projeto.

O SquashFS existente deve ser preservado conforme a estrutura atual do
repositório.

Resultados relevantes da engenharia reversa devem entrar como:

- documentação;
- testes;
- constantes justificadas;
- comentários técnicos pontuais.

Não como milhares de artefatos binários.

======================================================================
STAGING
======================================================================

Antes de cada commit use staging seletivo.

Evite cegamente:

git add .

quando houver arquivos não relacionados.

Prefira:

git add <arquivos relevantes>

ou:

git add -p

Antes de cada commit execute:

git diff --cached

e confirme que o commit contém somente a mudança lógica pretendida.

======================================================================
CHECKLIST ANTES DE CADA COMMIT
======================================================================

Antes de criar um commit confirme:

[ ] mudança possui um único objetivo lógico

[ ] não contém código temporário

[ ] não contém debug prints

[ ] não contém secrets

[ ] não contém dumps/binários temporários

[ ] não contém alterações do usuário preexistentes

[ ] testes relevantes passam

[ ] código compila

[ ] lint/typecheck passam quando aplicável

[ ] git diff --cached foi revisado

======================================================================
WIP COMMITS
======================================================================

Evite commits WIP no histórico final.

Durante desenvolvimento você pode criar commits temporários APENAS se necessário
para segurança do trabalho.

Antes da entrega:

- reorganize esses commits;
- faça fixup/rebase quando seguro;
- preserve commits semanticamente relevantes.

Não faça squash de tudo em um commit.

O objetivo final continua sendo múltiplos commits úteis.

======================================================================
FIXUP
======================================================================

Se uma correção pequena pertence claramente a um commit anterior ainda não
publicado, pode usar:

git commit --fixup=<commit>

e posteriormente:

git rebase -i --autosquash

SOMENTE se:

- a branch for exclusivamente sua;
- os commits ainda não tiverem sido compartilhados;
- isso não reescrever histórico de outras pessoas.

Nunca force-push ou reescreva histórico compartilhado sem autorização.

======================================================================
REBASE / MERGE
======================================================================

Não faça rebase da main/master nem force push automaticamente sem necessidade.

Se precisar atualizar a feature com a branch principal:

- primeiro verifique o padrão do projeto;
- preserve o histórico existente;
- resolva conflitos cuidadosamente;
- rode os testes novamente.

NÃO use:

git reset --hard

git clean -fd

git checkout -- .

ou comandos destrutivos equivalentes sem certeza absoluta de que não existem
mudanças do usuário.

======================================================================
DEPENDÊNCIAS
======================================================================

Se adicionar uma nova dependência:

faça isso no commit da primeira funcionalidade que realmente precisa dela,
ou em um commit próprio quando a alteração de build for relevante.

Exemplo:

build(radius): add RADIUS client dependency

seguido por:

feat(radius): implement portal RADIUS authentication

Não adicione dezenas de dependências preventivamente.

======================================================================
MIGRATIONS / CONFIG
======================================================================

Se houver mudanças em:

- schema;
- config;
- migrations;
- service definitions;
- systemd/init scripts;
- OpenWrt packages;
- UCI defaults;

mantenha essas mudanças junto à feature correspondente ou em commit próprio
quando tiverem lifecycle independente.

======================================================================
HISTÓRICO ESPERADO
======================================================================

Um histórico saudável para esta tarefa poderia parecer algo como:

refactor(client): centralize device client state

feat(protocol): add WLAN management message mappings

feat(wlan): add wireless network domain model

feat(openwrt): reconcile Omada WLANs with UCI

feat(vlan): apply SSID and management VLAN configuration

feat(dhcp): track wireless client IP leases

feat(inform): report WLAN and client state

feat(portal): add captive portal policy model

feat(portal): enforce unauthenticated clients with nftables

feat(portal): implement authenticated session lifecycle

feat(radius): integrate portal RADIUS authentication

feat(portal): add pre-auth domain access rules

test(portal): cover captive portal end-to-end lifecycle

fix(adoption): align negotiated capabilities with controller

docs(omada): update protocol and platform implementation notes

Isso é apenas um EXEMPLO.

Não force essa sequência se o código demonstrar dependências diferentes.

======================================================================
COMMITS E FUNCIONALIDADES
======================================================================

Evite quebrar funcionalidade só para manter commits pequenos.

"pequeno" não significa "incompleto".

Um commit ideal é:

ATÔMICO

e não:

MINÚSCULO.

======================================================================
PULL REQUEST READY
======================================================================

Antes de finalizar:

git status

deve estar limpo, exceto por arquivos do usuário que já existiam e que você
deliberadamente preservou.

Execute também:

git log --oneline <base>..HEAD

Revise o histórico inteiro.

Pergunte para cada commit:

"Um reviewer consegue entender por que esse commit existe?"

Se não, reorganize.

======================================================================
ENTREGA FINAL
======================================================================

Ao terminar, NÃO responda apenas "implementado".

Apresente:

1. nome da branch utilizada;

2. base utilizada;

3. lista dos commits em ordem:

   <hash curto> <mensagem>

4. resumo do que cada commit implementa;

5. testes executados;

6. resultado dos testes;

7. arquivos preexistentes/modificados pelo usuário que foram preservados;

8. eventuais limitações restantes;

9. se houve mudanças em adoption existente;

10. se algum commit ainda precisa ser reorganizado antes do merge.

Também forneça:

git log --oneline <base>..HEAD

como referência.

======================================================================
REGRA FINAL
======================================================================

Não faça:

git add .
git commit -m "implement everything"

no final da tarefa.

O histórico Git faz parte da qualidade da implementação.

Implemente em incrementos lógicos e faça commits conforme cada camada funcional
for ficando pronta e testada.