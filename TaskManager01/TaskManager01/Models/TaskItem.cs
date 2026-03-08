using System.ComponentModel.DataAnnotations;

namespace TaskManager01.Models
{
    public enum TaskStatus { Pending, InProgress, Completed }
    public enum TaskPriority { Low, Medium, High }

    public class TaskItem
    {
        public int Id { get; set; }

        [Required, StringLength(200)]
        public string Title { get; set; } = string.Empty;

        [StringLength(1000)]
        public string? Description { get; set; }

        public TaskStatus Status { get; set; } = TaskStatus.Pending;
        public TaskPriority Priority { get; set; } = TaskPriority.Medium;
        public DateTime? DueDate { get; set; }
        public DateTime CreatedAt { get; set; }
        public DateTime UpdatedAt { get; set; }
    }
}
