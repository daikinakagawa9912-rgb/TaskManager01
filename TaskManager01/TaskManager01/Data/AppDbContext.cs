using Microsoft.EntityFrameworkCore;
using TaskManager01.Models;

namespace TaskManager01.Data
{
    public class AppDbContext : DbContext
    {
        public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }
        public DbSet<TaskItem> Tasks { get; set; }
    }
}
