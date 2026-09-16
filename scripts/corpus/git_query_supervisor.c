/* Experimental X-03 feasibility supervisor. Not a product execution profile.
 * Trusted stdout is a bounded line protocol; child streams are hex encoded.
 * Policy checks run at ptrace exec-stop, before the new image runs user code.
 */
#define _GNU_SOURCE
#include <sys/ptrace.h>
#include <linux/ptrace.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <openssl/evp.h>

#define MAX_TASKS 3
#define CAPTURE 16384
#define VECTOR 32768
#define OPTIONS (PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK | \
                 PTRACE_O_TRACECLONE | PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL)
#define QUERY "git log --pretty=format:%ct --quiet -1 HEAD"
extern char **environ;
enum role { INITIAL, MAIN, SHELL, GIT };
struct task {
    pid_t pid, parent;
    enum role role;
    int alive, pending_fork;
    long syscall;
    double started;
};
static struct task tasks[MAX_TASKS];
static int count, children, failed, root_exit = -1, outfd, errfd;
static const char *reason = "none", *hashes[3];
static char **root_argv;
static unsigned long child_bytes;
static unsigned char out[CAPTURE], err[CAPTURE];
static size_t outn, errn;
static volatile sig_atomic_t tick;
static double root_started;
static unsigned root_wall;

static double now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) _exit(124);
    return ts.tv_sec + ts.tv_nsec / 1000000000.0;
}
static void alarm_tick(int sig) { (void)sig; tick = 1; }
static void refuse(const char *why) {
    if (!failed) { failed = 1; reason = why; }
    for (int i=0; i<count; i++) if (tasks[i].alive) kill(tasks[i].pid, SIGKILL);
}
static struct task *find_task(pid_t pid) {
    for (int i=0; i<count; i++) if (tasks[i].pid==pid) return &tasks[i];
    return NULL;
}
static ssize_t proc_read(pid_t pid, const char *name, char *buf, size_t cap) {
    char path[128];
    snprintf(path,sizeof(path),"/proc/%d/%s",pid,name);
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    if (fd<0) return -1;
    size_t used=0;
    while (used<cap) {
        ssize_t n=read(fd,buf+used,cap-used);
        if (n==0) break;
        if (n<0) { if(errno==EINTR) continue; close(fd); return -1; }
        used+=(size_t)n;
    }
    close(fd);
    return used==cap ? -1 : (ssize_t)used;
}
static int proc_link(pid_t pid, const char *name, char *buf, size_t cap) {
    char path[128];
    snprintf(path,sizeof(path),"/proc/%d/%s",pid,name);
    ssize_t n=readlink(path,buf,cap-1);
    if(n<0 || (size_t)n==cap-1) return 0;
    buf[n]=0;
    return 1;
}
static int hash_matches(pid_t pid, const char *expected) {
    char path[128]; unsigned char digest[EVP_MAX_MD_SIZE]; unsigned length=0;
    snprintf(path,sizeof(path),"/proc/%d/exe",pid);
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    if(fd<0) return 0;
    EVP_MD_CTX *ctx=EVP_MD_CTX_new();
    int ok=ctx && EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
    unsigned char buf[8192]; ssize_t n;
    while(ok && (n=read(fd,buf,sizeof(buf)))!=0) {
        if(n<0) { if(errno==EINTR) continue; ok=0; break; }
        ok=EVP_DigestUpdate(ctx,buf,(size_t)n)==1;
    }
    if(ok) ok=EVP_DigestFinal_ex(ctx,digest,&length)==1;
    if(ctx) EVP_MD_CTX_free(ctx);
    close(fd);
    char hex[65];
    if(!ok || length!=32) return 0;
    for(unsigned i=0;i<length;i++) snprintf(hex+2*i,3,"%02x",digest[i]);
    return strcmp(hex,expected)==0;
}
static int vector_matches(char *buf, size_t size, char *const wanted[]) {
    size_t at=0;
    for(size_t i=0; wanted[i]; i++) {
        size_t len=strlen(wanted[i])+1;
        if(len>size-at || memcmp(buf+at,wanted[i],len)) return 0;
        at+=len;
    }
    return at==size;
}
static int environment_matches(pid_t pid, const char *cwd) {
    char buf[VECTOR]; ssize_t size=proc_read(pid,"environ",buf,sizeof(buf));
    if(size<=0) return 0;
    size_t at=0;
    while(at<(size_t)size) {
        size_t len=strnlen(buf+at,(size_t)size-at);
        if(len==(size_t)size-at) return 0;
        int found=0;
        for(char **entry=environ;*entry;entry++) if(!strcmp(*entry,buf+at)) found=1;
        if(!strncmp(buf+at,"PWD=",4) && !strcmp(buf+at+4,cwd)) found=1;
        if(!found) return 0;
        at+=len+1;
    }
    return 1;
}
static int exec_check(struct task *t) {
    char exe[PATH_MAX], cwd[PATH_MAX], args[VECTOR];
    if(!proc_link(t->pid,"exe",exe,sizeof(exe)) ||
       !proc_link(t->pid,"cwd",cwd,sizeof(cwd))) return 0;
    if(strncmp(cwd,"/attest/tree",12) || (cwd[12] && cwd[12]!='/')) return 0;
    ssize_t size=proc_read(t->pid,"cmdline",args,sizeof(args));
    if(size<=0 || !environment_matches(t->pid,cwd)) return 0;
    int hash_index;
    enum role next;
    if(t==&tasks[0] && t->role==INITIAL) {
        char target[PATH_MAX];
        if(!realpath(root_argv[0],target) || strcmp(exe,target) ||
           !vector_matches(args,(size_t)size,root_argv)) return 0;
        hash_index=0; next=MAIN;
    } else if(t!=&tasks[0] && t->role==INITIAL && find_task(t->parent) &&
              find_task(t->parent)->role==MAIN) {
        struct task *parent=find_task(t->parent);
        char *shell[]={"/bin/sh","-c",QUERY,NULL};
        char target[PATH_MAX];
        if(!parent || parent->role!=MAIN || !realpath("/bin/sh",target) ||
           strcmp(exe,target) || !vector_matches(args,(size_t)size,shell)) return 0;
        hash_index=1; next=SHELL;
    } else if(t->role==SHELL || (t->role==INITIAL && find_task(t->parent) &&
                               find_task(t->parent)->role==SHELL)) {
        char *git[]={"git","log","--pretty=format:%ct","--quiet","-1","HEAD",NULL};
        char target[PATH_MAX];
        if(!realpath("/usr/bin/git",target) || strcmp(exe,target) ||
           !vector_matches(args,(size_t)size,git)) return 0;
        hash_index=2; next=GIT;
    } else return 0;
    if(!hash_matches(t->pid,hashes[hash_index])) return 0;
    t->role=next;
    printf("EXEC %d %d %d\n",t->pid,t->parent,t->role);
    return 1;
}
static int syscall_is_fork(long nr) {
    return nr==SYS_clone
#ifdef SYS_clone3
        || nr==SYS_clone3
#endif
#ifdef SYS_fork
        || nr==SYS_fork
#endif
#ifdef SYS_vfork
        || nr==SYS_vfork
#endif
        ;
}
static int is_open(long nr) {
    return nr==SYS_openat
#ifdef SYS_open
        || nr==SYS_open
#endif
#ifdef SYS_openat2
        || nr==SYS_openat2
#endif
        ;
}
static int blocked_syscall(long nr) {
    return nr==SYS_ptrace || nr==SYS_process_vm_writev || nr==SYS_process_vm_readv
#ifdef SYS_pidfd_getfd
        || nr==SYS_pidfd_getfd
#endif
#ifdef SYS_io_uring_setup
        || nr==SYS_io_uring_setup
#endif
#ifdef SYS_io_setup
        || nr==SYS_io_setup
#endif
#ifdef SYS_open_by_handle_at
        || nr==SYS_open_by_handle_at
#endif
#ifdef SYS_execveat
        || nr==SYS_execveat
#endif
        ;
}
static int safe_open(struct task *t, long result) {
    if(result<0) return 1;
    char entry[64], path[PATH_MAX];
    snprintf(entry,sizeof(entry),"fd/%ld",result);
    if(!proc_link(t->pid,entry,path,sizeof(path))) return 0;
    const char *last=strrchr(path,'/');
    if(!strncmp(path,"/proc/",6) && last && !strcmp(last,"/mem")) return 0;
    return 1;
}
static void syscall_check(struct task *t) {
    struct ptrace_syscall_info info;
    memset(&info,0,sizeof(info));
    long n=ptrace(PTRACE_GET_SYSCALL_INFO,t->pid,sizeof(info),&info);
    if(n<0) { refuse("syscall-inspection"); return; }
    if(info.op==PTRACE_SYSCALL_INFO_ENTRY) {
        long nr=(long)info.entry.nr;
        t->syscall=nr;
        if(blocked_syscall(nr)) { refuse("forbidden-syscall"); return; }
        if(syscall_is_fork(nr)) {
            int reserved=children;
            for(int i=0;i<count;i++) reserved+=tasks[i].pending_fork;
            if(reserved>=2 || (t->role!=MAIN && t->role!=SHELL)) {
                refuse("child-budget-or-parent"); return;
            }
            /* clone3 uses pointer arguments; do not authorize a mutable flags
             * buffer. This prototype refuses it rather than silently loosening.
             */
#ifdef SYS_clone3
            if(nr==SYS_clone3) { refuse("clone3-unsupported"); return; }
#endif
            if(nr==SYS_clone && (info.entry.args[0] & (0x400UL | 0x10000UL))) {
                refuse("shared-files-or-thread"); return;
            }
            t->pending_fork=1;
        }
        if(t!=&tasks[0]) {
            if(nr==SYS_write || nr==SYS_pwrite64) {
                unsigned long size=info.entry.args[2];
                if(size>CAPTURE || child_bytes>CAPTURE-size) {
                    refuse("child-output-limit"); return;
                }
                child_bytes+=size;
            }
            if(nr==SYS_writev || nr==SYS_sendfile || nr==SYS_splice || nr==SYS_vmsplice
#ifdef SYS_pwritev
               || nr==SYS_pwritev
#endif
#ifdef SYS_pwritev2
               || nr==SYS_pwritev2
#endif
#ifdef SYS_copy_file_range
               || nr==SYS_copy_file_range
#endif
               ) refuse("unmetered-child-output");
        }
    } else if(info.op==PTRACE_SYSCALL_INFO_EXIT) {
        if(t->pending_fork && syscall_is_fork(t->syscall)) t->pending_fork=0;
        if(is_open(t->syscall) && !safe_open(t,(long)info.exit.rval)) refuse("proc-memory-fd");
    } else refuse("unknown-syscall-stop");
}
static void drain(int fd,unsigned char *buf,size_t *used) {
    unsigned char scratch[4096]; ssize_t n;
    while((n=read(fd,scratch,sizeof(scratch)))>0) {
        if((size_t)n>CAPTURE-*used) { refuse("root-output-limit"); return; }
        memcpy(buf+*used,scratch,(size_t)n); *used+=(size_t)n;
    }
    if(n<0 && errno!=EINTR && errno!=EAGAIN) refuse("capture-read");
}
static void hex(const unsigned char *buf,size_t size) {
    for(size_t i=0;i<size;i++) printf("%02x",buf[i]);
    putchar('\n');
}
static int child_limits(pid_t pid) {
    struct rlimit cpu={5,5}, memory={128UL*1024*1024,128UL*1024*1024};
    struct rlimit files={CAPTURE,CAPTURE}, core={0,0};
    return !prlimit(pid,RLIMIT_CPU,&cpu,NULL) && !prlimit(pid,RLIMIT_AS,&memory,NULL)
        && !prlimit(pid,RLIMIT_FSIZE,&files,NULL) && !prlimit(pid,RLIMIT_CORE,&core,NULL);
}
int main(int argc,char **argv) {
    if(argc<7 || strcmp(argv[5],"--") || argv[6][0]!='/') return 120;
    for(int i=0;i<3;i++) { if(strlen(argv[i+1])!=64) return 120; hashes[i]=argv[i+1]; }
    char *end; unsigned long wall=strtoul(argv[4],&end,10);
    if(*end || wall<1 || wall>300) return 120;
    root_wall=(unsigned)wall; root_argv=&argv[6];
    /* The trusted caller must start this supervisor in a clean environment. */
    for(char **e=environ;*e;e++)
        if(!strncmp(*e,"LD_",3) || !strncmp(*e,"BASH_ENV=",9) || !strncmp(*e,"ENV=",4)) return 120;
    if(prctl(PR_SET_DUMPABLE,0) || prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) return 120;
    int op[2], ep[2];
    if(pipe2(op,O_CLOEXEC) || pipe2(ep,O_CLOEXEC)) return 120;
    pid_t root=fork();
    if(root<0) return 120;
    if(root==0) {
        close(op[0]); close(ep[0]);
        if(dup2(op[1],STDOUT_FILENO)<0 || dup2(ep[1],STDERR_FILENO)<0) _exit(120);
        close(op[1]); close(ep[1]);
        /* Undo only our own dumpability setting so the parent can inspect us. */
        if(prctl(PR_SET_DUMPABLE,1) || ptrace(PTRACE_TRACEME,0,NULL,NULL)<0) _exit(120);
        raise(SIGSTOP);
        execv(root_argv[0],root_argv);
        _exit(120);
    }
    close(op[1]); close(ep[1]); outfd=op[0]; errfd=ep[0];
    fcntl(outfd,F_SETFL,O_NONBLOCK); fcntl(errfd,F_SETFL,O_NONBLOCK);
    root_started=now();
    tasks[0]=(struct task){.pid=root,.role=INITIAL,.alive=1,.syscall=-1,.started=root_started};
    count=1;
    printf("ATTEST-GQ-PROTOTYPE-1\n");
    struct sigaction sa={0}; sa.sa_handler=alarm_tick; sigemptyset(&sa.sa_mask);
    sigaction(SIGALRM,&sa,NULL);
    struct itimerval timer={{0,10000},{0,10000}};
    setitimer(ITIMER_REAL,&timer,NULL);
    for(;;) {
        drain(outfd,out,&outn); drain(errfd,err,&errn);
        if(tick) {
            tick=0; double current=now();
            if(current-root_started>root_wall) refuse("root-wall-limit");
            for(int i=1;i<count;i++)
                if(tasks[i].alive && current-tasks[i].started>5) refuse("child-wall-limit");
        }
        int status; struct rusage usage;
        pid_t pid=wait4(-1,&status,__WALL,&usage);
        if(pid<0) { if(errno==EINTR) continue; if(errno==ECHILD) break; refuse("wait"); break; }
        struct task *t=find_task(pid);
        if(!t) { kill(pid,SIGKILL); refuse("untracked-task"); continue; }
        if(WIFEXITED(status) || WIFSIGNALED(status)) {
            int exit_status=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
            t->alive=0;
            if(t==&tasks[0]) root_exit=exit_status;
            else if(t->role!=GIT) {
                int completed=0;
                for(int i=1;i<count;i++)
                    if(tasks[i].parent==pid && tasks[i].role==GIT && !tasks[i].alive) completed=1;
                if(t->role!=SHELL || !completed) refuse("incomplete-child-chain");
            }
            printf("EXIT %d %d %ld\n",pid,exit_status,usage.ru_maxrss);
            continue;
        }
        if(!WIFSTOPPED(status)) { refuse("unknown-wait-status"); continue; }
        unsigned event=(unsigned)status>>16; int sig=WSTOPSIG(status), deliver=0;
        if(event==PTRACE_EVENT_FORK || event==PTRACE_EVENT_VFORK || event==PTRACE_EVENT_CLONE) {
            unsigned long child=0;
            if(ptrace(PTRACE_GETEVENTMSG,pid,NULL,&child)<0 || count==MAX_TASKS ||
               !t->pending_fork || !child_limits((pid_t)child)) {
                if(child) kill((pid_t)child,SIGKILL);
                refuse("child-registration");
            } else {
                t->pending_fork=0; children++;
                tasks[count++]=(struct task){.pid=(pid_t)child,.parent=pid,.role=INITIAL,
                                             .alive=1,.syscall=-1,.started=now()};
                printf("FORK %d %lu\n",pid,child);
            }
        } else if(event==PTRACE_EVENT_EXEC) {
            if(!exec_check(t)) refuse("executable-arguments-environment-or-cwd");
        } else if(event) refuse("unknown-ptrace-event");
        else if(sig==(SIGTRAP|0x80)) syscall_check(t);
        else if(sig==SIGSTOP) {
            if(ptrace(PTRACE_SETOPTIONS,pid,NULL,OPTIONS)<0) refuse("trace-options");
        } else deliver=sig;
        if(failed) kill(pid,SIGKILL);
        else if(ptrace(PTRACE_SYSCALL,pid,NULL,(void*)(long)deliver)<0) refuse("resume");
    }
    drain(outfd,out,&outn); drain(errfd,err,&errn);
    printf("RESULT %d %d %s %lu\n",failed,root_exit,reason,child_bytes);
    printf("STDOUT "); hex(out,outn);
    printf("STDERR "); hex(err,errn);
    return failed?121:root_exit;
}
