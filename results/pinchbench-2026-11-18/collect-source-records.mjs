import fs from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Read-only source collection: never imports or runs downloaded benchmark code.
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const output=path.join(root,'projects/benchclaw/content/keyword-research/bc137-source-records-2026-11-18.json');
const extra=process.argv.includes('--extra');
const sources=extra?[
 ['benchmark','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/scripts/benchmark.py'],
 ['task-loader','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/scripts/lib/task_loader.py'],
]:[
 ['repository','https://api.github.com/repos/pinchbench/skill'],
 ['release','https://api.github.com/repos/pinchbench/skill/releases?per_page=1'],
 ['advisories','https://api.github.com/repos/pinchbench/skill/security-advisories'],
 ['tree','https://api.github.com/repos/pinchbench/skill/git/trees/819384ae830492365b8363fc26bc2602e73f216d?recursive=1'],
 ['readme','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/README.md'],
 ['manifest','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/tasks/manifest.yaml'],
 ['version','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/BENCHMARK_VERSION'],
 ['runner','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/scripts/run.sh'],
 ['license','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/LICENSE'],
 ['about','https://pinchbench.com/about'],
 ['official-runner','https://raw.githubusercontent.com/pinchbench/scripts/92a27eca2f57af0194aa89ff4c9ea3d0e2ca2661/bench_runner.sh'],
 ['official-models','https://raw.githubusercontent.com/pinchbench/scripts/92a27eca2f57af0194aa89ff4c9ea3d0e2ca2661/default-models.yml'],
 ['task-calendar','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/tasks/task_calendar.md'],
 ['task-blog','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/tasks/task_blog.md'],
 ['task-csv','https://raw.githubusercontent.com/pinchbench/skill/819384ae830492365b8363fc26bc2602e73f216d/tasks/task_csv_cities_ranking.md'],
];
const strip=s=>s.replace(/<script[\s\S]*?<\/script>/gi,' ').replace(/<style[\s\S]*?<\/style>/gi,' ').replace(/<[^>]+>/g,' ').replace(/&nbsp;|&#160;/g,' ').replace(/&amp;/g,'&').replace(/&#x27;/g,"'").replace(/\s+/g,' ').trim();
const report=extra?JSON.parse(await fs.readFile(output,'utf8')):{checked_at:new Date().toISOString(),method:'Public documentation and static source inspection only; no benchmark installation, model call or result upload.',skill_commit:'819384ae830492365b8363fc26bc2602e73f216d',scripts_commit:'92a27eca2f57af0194aa89ff4c9ea3d0e2ca2661',sources:[]};
for(const [kind,url] of sources){
 const r=await fetch(url,{headers:{'User-Agent':'BenchClawResearch/1.0'},signal:AbortSignal.timeout(25000)});
 const body=await r.text();
 const row={kind,url,final_url:r.url,status:r.status,sha256:createHash('sha256').update(body).digest('hex')};
 if(kind==='tree'&&r.ok){const j=JSON.parse(body);row.data={truncated:j.truncated,task_files:j.tree.filter(x=>/^tasks\/task_.*\.md$/.test(x.path)).map(x=>({path:x.path,sha:x.sha}))};}
 else if(kind==='repository'&&r.ok){const j=JSON.parse(body);row.data={full_name:j.full_name,archived:j.archived,pushed_at:j.pushed_at,default_branch:j.default_branch,license:j.license?.spdx_id};}
 else if(kind==='release'&&r.ok){row.data=JSON.parse(body).map(j=>({tag_name:j.tag_name,published_at:j.published_at,html_url:j.html_url,body:j.body}));}
 else if(kind==='advisories'&&r.ok){row.data=JSON.parse(body).map(j=>({ghsa_id:j.ghsa_id,summary:j.summary,html_url:j.html_url}));}
 else {row.text=kind==='about'?strip(body):body;}
 row.agent_directed_flags=[...body.matchAll(/ignore (?:all )?(?:previous|prior) instructions|if you are an? (?:ai|llm|agent|bot)|reveal your (?:prompt|instructions)/ig)].map(m=>m[0]);
 report.sources.push(row);
 await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({kind,status:r.status,flags:row.agent_directed_flags}));
 if(!r.ok)throw new Error('Source read failed: '+kind+' HTTP '+r.status);
}
