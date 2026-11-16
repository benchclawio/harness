import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';

const out = process.argv.find(arg=>arg.startsWith('--output='))?.slice('--output='.length) || 'projects/benchclaw/content/keyword-research/bc136-n8n-evidence-2026-11-16.json';
const repos = ['n8n-io/n8n', 'activepieces/activepieces', 'windmill-labs/windmill', 'langgenius/dify', 'FlowiseAI/Flowise'];
const pages = [
  'https://blog.n8n.io/introducing-n8n-agents/',
  'https://docs.n8n.io/build/build-and-manage-agents/',
  'https://docs.n8n.io/sustainable-use-license/',
  'https://n8n.io/pricing/',
  'https://www.activepieces.com/',
  'https://www.windmill.dev/docs/intro',
  'https://dify.ai/',
  'https://flowiseai.com/',
  'https://zapier.com/pricing',
  'https://www.make.com/en/pricing',
  'https://www.make.com/en/ai-agents',
  'https://zapier.com/agents',
  'https://flowiseai.com/sunset',
  'https://raw.githubusercontent.com/activepieces/activepieces/main/README.md',
  'https://raw.githubusercontent.com/windmill-labs/windmill/main/README.md',
  'https://raw.githubusercontent.com/langgenius/dify/main/README.md',
  'https://raw.githubusercontent.com/FlowiseAI/Flowise/main/README.md',
];
const extra = process.argv.includes('--extra');
const report = extra ? JSON.parse(await fs.readFile(out,'utf8')) : {checked_at: new Date().toISOString(), kind:'public-records audit; no products installed or agents run', sources:[]};
const strip = s => s.replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/\s+/g,' ').trim();
async function get(url, type, repo) {
  const r=await fetch(url,{headers:{'User-Agent':'BenchClawResearch/1.0','Accept':'application/vnd.github+json'},signal:AbortSignal.timeout(25000)});
  const body=await r.text();
  const row={url,final_url:r.url,status:r.status,type,repo,sha256:createHash('sha256').update(body).digest('hex')};
  if(r.ok && type!=='page'){
    const d=JSON.parse(body);
    if(type==='repo')row.data={full_name:d.full_name,archived:d.archived,pushed_at:d.pushed_at,default_branch:d.default_branch,license:d.license,description:d.description,homepage:d.homepage};
    if(type==='release')row.data={tag_name:d.tag_name,published_at:d.published_at,html_url:d.html_url,prerelease:d.prerelease,body:d.body};
    if(type==='license')row.data={path:d.path,html_url:d.html_url,license:d.license,text:Buffer.from(d.content||'','base64').toString('utf8')};
    if(type==='advisories')row.data=d.map(a=>({ghsa_id:a.ghsa_id,summary:a.summary,severity:a.severity,published_at:a.published_at,html_url:a.html_url,vulnerabilities:a.vulnerabilities}));
  } else if(r.ok){
    const text=strip(body);
    row.title=strip(body.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]||'');
    // Bounded public-page excerpts, retained for claim checking, not page republication.
    const terms=/agents?|preview|execution|credit|task|sustainable|licen[cs]e|open.source|acquir|workday|self.host|free|memory|skills|channels|approvals/ig;
    const spans=[];for(const m of text.matchAll(terms)){if(spans.length>=25)break;const start=Math.max(0,m.index-140),end=Math.min(text.length,m.index+550);if(!spans.some(s=>start<s.end))spans.push({start,end,text:text.slice(start,end)});}
    row.excerpts=spans.map(s=>s.text);
    row.agent_directed_flags=[...body.matchAll(/ignore (?:all )?(?:previous|prior) instructions|if you are an? (?:ai|llm|agent|bot)|reveal your (?:prompt|instructions)/ig)].map(m=>m[0]);
  }
  report.sources.push(row);
  console.log(JSON.stringify({type,repo,url,status:r.status,flags:row.agent_directed_flags}));
  await fs.writeFile(out,JSON.stringify(report,null,2)+'\n');
  return row;
}
for(const repo of extra ? [] : repos){
  for(const [suffix,type] of [['','repo'],['/releases/latest','release'],['/license','license'],['/security-advisories?per_page=10','advisories']]){
    await get('https://api.github.com/repos/'+repo+suffix,type,repo);
  }
}
for(const url of extra ? ['https://flowiseai.com/sunset','https://raw.githubusercontent.com/activepieces/activepieces/main/README.md','https://raw.githubusercontent.com/windmill-labs/windmill/main/README.md','https://raw.githubusercontent.com/langgenius/dify/main/README.md','https://raw.githubusercontent.com/FlowiseAI/Flowise/main/README.md'] : pages)await get(url,'page');
