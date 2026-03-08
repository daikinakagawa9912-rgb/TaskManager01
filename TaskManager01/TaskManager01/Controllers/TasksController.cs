using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using TaskManager01.Data;
using TaskManager01.Models;

namespace TaskManager01.Controllers
{
    public class TasksController : Controller
    {
        private readonly AppDbContext _context;

        public TasksController(AppDbContext context)
        {
            _context = context;
        }

        public async Task<IActionResult> Index(string? statusFilter, string? priorityFilter, string? sortBy)
        {
            var query = _context.Tasks.AsQueryable();

            if (!string.IsNullOrEmpty(statusFilter) && Enum.TryParse<Models.TaskStatus>(statusFilter, out var status))
                query = query.Where(t => t.Status == status);

            if (!string.IsNullOrEmpty(priorityFilter) && Enum.TryParse<TaskPriority>(priorityFilter, out var priority))
                query = query.Where(t => t.Priority == priority);

            query = sortBy switch
            {
                "title" => query.OrderBy(t => t.Title),
                "priority" => query.OrderByDescending(t => t.Priority),
                "duedate" => query.OrderBy(t => t.DueDate),
                _ => query.OrderByDescending(t => t.CreatedAt)
            };

            ViewBag.StatusFilter = statusFilter;
            ViewBag.PriorityFilter = priorityFilter;
            ViewBag.SortBy = sortBy;

            return View(await query.ToListAsync());
        }

        public async Task<IActionResult> Details(int? id)
        {
            if (id == null) return NotFound();
            var task = await _context.Tasks.FirstOrDefaultAsync(t => t.Id == id);
            if (task == null) return NotFound();
            return View(task);
        }

        public IActionResult Create()
        {
            return View();
        }

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Create([Bind("Title,Description,Status,Priority,DueDate")] TaskItem task)
        {
            if (ModelState.IsValid)
            {
                task.CreatedAt = DateTime.UtcNow;
                task.UpdatedAt = DateTime.UtcNow;
                _context.Add(task);
                await _context.SaveChangesAsync();
                return RedirectToAction(nameof(Index));
            }
            return View(task);
        }

        public async Task<IActionResult> Edit(int? id)
        {
            if (id == null) return NotFound();
            var task = await _context.Tasks.FindAsync(id);
            if (task == null) return NotFound();
            return View(task);
        }

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Edit(int id, [Bind("Id,Title,Description,Status,Priority,DueDate,CreatedAt")] TaskItem task)
        {
            if (id != task.Id) return NotFound();

            if (ModelState.IsValid)
            {
                try
                {
                    task.UpdatedAt = DateTime.UtcNow;
                    _context.Update(task);
                    await _context.SaveChangesAsync();
                }
                catch (DbUpdateConcurrencyException)
                {
                    if (!_context.Tasks.Any(t => t.Id == task.Id)) return NotFound();
                    throw;
                }
                return RedirectToAction(nameof(Index));
            }
            return View(task);
        }

        public async Task<IActionResult> Delete(int? id)
        {
            if (id == null) return NotFound();
            var task = await _context.Tasks.FirstOrDefaultAsync(t => t.Id == id);
            if (task == null) return NotFound();
            return View(task);
        }

        [HttpPost, ActionName("Delete")]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> DeleteConfirmed(int id)
        {
            var task = await _context.Tasks.FindAsync(id);
            if (task != null) _context.Tasks.Remove(task);
            await _context.SaveChangesAsync();
            return RedirectToAction(nameof(Index));
        }
    }
}
